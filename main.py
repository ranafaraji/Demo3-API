import json
import hashlib
from typing import Optional
from fastapi import FastAPI, HTTPException, Request, Response, Header, Depends
from jsonschema import validate
import redis
from worker import sync_to_es
#rana
app = FastAPI(title="Demo 3 API")
r = redis.Redis(host="localhost", port=6379, decode_responses=True)

with open("plan.schema.json", "r") as f:
    PLAN_SCHEMA = json.load(f)

def compute_etag(data: dict) -> str:
    return hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()

def merge_patch(target: dict, patch: dict) -> dict:
    for k, v in patch.items():
        if v is None:
            target.pop(k, None)
        elif isinstance(v, list) and k in target and isinstance(target[k], list):
            target_map = {item["objectId"]: item for item in target[k] if "objectId" in item}
            for patch_item in v:
                if "objectId" in patch_item and patch_item["objectId"] in target_map:
                    merge_patch(target_map[patch_item["objectId"]], patch_item)
                else:
                    target[k].append(patch_item)
        elif isinstance(v, dict) and k in target and isinstance(target[k], dict):
            merge_patch(target[k], v)
        else:
            target[k] = v
    return target

@app.post("/v3/plan", status_code=201)
async def create_plan(request: Request, response: Response):
    payload = await request.json()
    validate(instance=payload, schema=PLAN_SCHEMA)
    
    plan_id = payload["objectId"]
    if r.exists(f"plan:{plan_id}"):
        raise HTTPException(status_code=409, detail="Plan already exists")

    etag = compute_etag(payload)
    r.set(f"plan:{plan_id}", json.dumps(payload))
    r.set(f"etag:{plan_id}", etag)
    
    sync_to_es.delay("INDEX", plan_id, payload)
    
    response.headers["ETag"] = etag
    return payload

@app.get("/v3/plan/{plan_id}")
async def get_plan(plan_id: str, response: Response, if_none_match: Optional[str] = Header(None)):
    data = r.get(f"plan:{plan_id}")
    if not data:
        raise HTTPException(status_code=404)
    
    plan = json.loads(data)
    etag = r.get(f"etag:{plan_id}")

    if if_none_match == etag:
        return Response(status_code=304)

    response.headers["ETag"] = etag
    return plan

@app.patch("/v3/plan/{plan_id}")
async def patch_plan(plan_id: str, request: Request, response: Response, if_match: str = Header(...)):
    raw_data = r.get(f"plan:{plan_id}")
    if not raw_data:
        raise HTTPException(status_code=404)
    
    current_etag = r.get(f"etag:{plan_id}")
    if if_match != current_etag:
        raise HTTPException(status_code=412, detail="ETag mismatch")

    patch_doc = await request.json()
    existing_plan = json.loads(raw_data)
    
    updated_plan = merge_patch(existing_plan, patch_doc)
    validate(instance=updated_plan, schema=PLAN_SCHEMA)

    new_etag = compute_etag(updated_plan)
    r.set(f"plan:{plan_id}", json.dumps(updated_plan))
    r.set(f"etag:{plan_id}", new_etag)

    # Pass the FULL updated_plan to the worker for re-indexing
    sync_to_es.delay("UPDATE", plan_id, updated_plan)

    response.headers["ETag"] = new_etag
    return updated_plan

@app.delete("/v3/plan/{plan_id}", status_code=204)
async def delete_plan(plan_id: str):
    if not r.exists(f"plan:{plan_id}"):
        raise HTTPException(status_code=404)

    r.delete(f"plan:{plan_id}")
    r.delete(f"etag:{plan_id}")

    sync_to_es.delay("DELETE", plan_id)
    return Response(status_code=204)