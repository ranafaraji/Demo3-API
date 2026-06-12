from elasticsearch import Elasticsearch

# Initialize the Elasticsearch client
es = Elasticsearch("http://localhost:9200")

def setup_elasticsearch():
    index_name = "plan_index"

    # Delete the index if it already exists to ensure a clean slate
    if es.indices.exists(index=index_name):
        es.indices.delete(index=index_name)

    mapping = {
        "mappings": {
            "properties": {
                # 1. Multi-level Join Field to support your specific queries
                "plan_relation": {
                    "type": "join",
                    "relations": {
                        "plan": ["planCostShares", "linkedPlanServices"],
                        "linkedPlanServices": ["planserviceCostShares"]
                    }
                },
                "objectId": { "type": "keyword" },
                "_org": { "type": "keyword" },
                "planType": { "type": "keyword" },
                # 2. Updated date format to support "12-12-2017"
                "creationDate": {
                    "type": "date",
                    "format": "dd-MM-yyyy||strict_date_optional_time||epoch_millis"
                },
                "name": {
                    "type": "text",
                    "fields": {
                        "keyword": { "type": "keyword" }
                    }
                },
                "copay": { "type": "integer" },
                "deductible": { "type": "integer" },
                "objectType": { "type": "keyword" }
            }
        }
    }

    # Create the index with the updated mapping
    es.indices.create(index=index_name, body=mapping)
    print(f"Index '{index_name}' created successfully with Parent-Child support!")

if __name__ == "__main__":
    setup_elasticsearch()