# Azure_Airbnb_CosmosDB_Near_RealTime_Project
This repo contains details about building near real time pipeline using Azure ADLS, CosmosDB and building Facts and Dimensions in Synapse Dedicated SQL Warehouse/Database and leveraging n8n to build workflow and send booking confirmation email, Thanks

**Project End to End Documentation:**


# Azure Airbnb CosmosDB Near-RealTime Project

A step-by-step README to get the Azure-based near-real-time pipeline for Airbnb data up and running. This guide covers architecture, prerequisites, local development, Azure resource provisioning, deployment, testing, observability, and troubleshooting.

> NOTE: Replace placeholder names and values with your organization/project-specific ones (resource group, region, resource names, keys, etc.).

## Table of contents
1. Project overview
2. Architecture
3. Prerequisites
4. Quick start — local
5. Provision Azure resources (step-by-step)
6. Configure and deploy processing components
7. Ingest sample data
8. Validate data in Cosmos DB
9. Observability and monitoring
10. CI/CD (recommended)
11. Testing
12. Cost & security considerations
13. Troubleshooting
14. Contributing
15. License

---

## 1. Project overview
This project demonstrates a near-real-time data ingestion and persistence pipeline for Airbnb-style data using Azure services:
- Ingest events/messages (e.g., listing changes, bookings) via an event streaming service.
- Process events in near-real-time and write to Azure Cosmos DB for low-latency reads.
- Provide a simple consumer/UI or analytics layer to read from Cosmos DB.

Core components (examples):
- Event ingestion: Azure Event Hubs (or Event Grid)
- Stream processing: Azure Functions (Event Hub trigger) or Stream Analytics
- Data store: Azure Cosmos DB (Core/SQL API)
- Optional: Application Insights, Power BI / simple web UI for visualization

---

## 2. Architecture (logical)
- Producer (script, app) -> Event Hub
- Event Hub -> Azure Function (EventHub trigger) -> transformation/validation -> Cosmos DB (insert/upsert)
- Consumers (web app, BI, dashboards) query Cosmos DB directly
- Monitoring via Application Insights and Azure Monitor

---

## 3. Prerequisites
- Azure subscription
- Azure CLI installed and logged in (az login)
- Optional: Azure Functions Core Tools (if using Azure Functions locally)
- Optional: .NET SDK, Node.js, or Python depending on function runtime used by this repo
- Git
- (Optional) Docker if containerizing services
- Recommended: an editor (VS Code)

---

## 4. Quick start — local
1. Clone the repository:
   ```bash
   git clone https://github.com/ViinayKumaarMamidi/Azure_Airbnb_CosmosDB_Near_RealTime_Project.git
   cd Azure_Airbnb_CosmosDB_Near_RealTime_Project
   ```

2. Inspect project folders:
   - `producer/` — example producer code that sends events to Event Hub
   - `functions/` — Azure Function(s) that process events and write to Cosmos DB
   - `infrastructure/` — (optional) ARM / Bicep / Terraform templates
   - `data/` — sample data files
   - `docs/` — additional documentation

3. Create a local config file (example `.env.local` / `local.settings.json` for Functions):
   ```
   # Example .env
   EVENTHUB_CONNECTION_STRING="<your-eventhub-connection-string>"
   EVENTHUB_NAME="<your-eventhub-name>"
   COSMOSDB_CONNECTION_STRING="<your-cosmosdb-connection-string>"
   COSMOSDB_DATABASE="airbnb"
   COSMOSDB_CONTAINER="listings"
   ```

4. Run producer locally (example):
   ```bash
   # Python example
   cd producer
   pip install -r requirements.txt
   python producer.py --file ../data/airbnb_sample.csv
   ```
   This will send events to your configured Event Hub.

5. Start functions locally:
   ```bash
   cd functions
   func start
   ```
   Ensure `local.settings.json` contains the required connection strings.

---

## 5. Provision Azure resources (step-by-step)
Below are sample Azure CLI commands. Modify names, regions, SKUs, and other options as needed.

1. Set variables:
   ```bash
   export RG="rg-airbnb-nearreal"
   export LOCATION="eastus"
   export COSMOS_ACCOUNT="airbnb-cosmos-$(date +%s | tail -c 6)"
   export EH_NAMESPACE="airbnbehns-$(date +%s | tail -c 6)"
   export EH_NAME="airbnb-events"
   export FUNCAPP_NAME="airbnb-func-$(date +%s | tail -c 6)"
   ```

2. Create a resource group:
   ```bash
   az group create --name $RG --location $LOCATION
   ```

3. Create an Event Hubs namespace + hub:
   ```bash
   az eventhubs namespace create --resource-group $RG --name $EH_NAMESPACE --location $LOCATION --sku Standard
   az eventhubs eventhub create --resource-group $RG --namespace-name $EH_NAMESPACE --name $EH_NAME --partition-count 2 --message-retention 1
   ```

4. Create Cosmos DB account (Core/SQL API):
   ```bash
   az cosmosdb create --name $COSMOS_ACCOUNT --resource-group $RG --locations regionName=$LOCATION --default-consistency-level Session
   ```

5. Create Cosmos SQL database and container:
   ```bash
   # Create database
   az cosmosdb sql database create --account-name $COSMOS_ACCOUNT --resource-group $RG --name airbnb

   # Create container with partition key /listingId and throughput
   az cosmosdb sql container create \
     --account-name $COSMOS_ACCOUNT \
     --resource-group $RG \
     --database-name airbnb \
     --name listings \
     --partition-key-path "/listingId" \
     --throughput 400
   ```

6. Get connection strings:
   ```bash
   # Event Hub connection string for producer (SAS policy "RootManageSharedAccessKey" or custom)
   az eventhubs namespace authorization-rule keys list --resource-group $RG --namespace-name $EH_NAMESPACE --name RootManageSharedAccessKey

   # Cosmos DB connection string
   az cosmosdb keys list --name $COSMOS_ACCOUNT --resource-group $RG --type connection-strings
   ```

7. (Optional) Create a Function App (Linux, Consumption plan) and configure app settings:
   ```bash
   # Storage account (required for Functions)
   export STORAGE_NAME="funcstorage$(date +%s | tail -c 6)"
   az storage account create --name $STORAGE_NAME --resource-group $RG --location $LOCATION --sku Standard_LRS

   # Create function app
   az functionapp create \
     --resource-group $RG \
     --consumption-plan-location $LOCATION \
     --runtime python \
     --functions-version 4 \
     --name $FUNCAPP_NAME \
     --storage-account $STORAGE_NAME

   # Set application settings (EventHub connection, Cosmos DB connection/keys)
   az functionapp config appsettings set --name $FUNCAPP_NAME --resource-group $RG --settings \
     EVENTHUB_CONNECTION_STRING="<value>" \
     EVENTHUB_NAME="$EH_NAME" \
     COSMOSDB_CONNECTION_STRING="<value>" \
     COSMOSDB_DATABASE="airbnb" \
     COSMOSDB_CONTAINER="listings"
   ```

Notes:
- Use managed identities where possible instead of connection strings for production.
- Consider RBAC and least privilege.

---

## 6. Configure and deploy processing components
This repo may include an Azure Function or other processor. Steps below assume Azure Functions:

1. Update configuration:
   - Edit `functions/local.settings.json` (for local) or set App Settings in Azure as shown above.
   - Ensure `FUNCTIONS_WORKER_RUNTIME` matches runtime (python/node/dotnet).

2. Install dependencies and test locally:
   ```bash
   cd functions
   pip install -r requirements.txt    # Python example
   func start
   ```

3. Deploy to Azure (examples):
   - Using Azure Functions Core Tools:
     ```bash
     func azure functionapp publish $FUNCAPP_NAME
     ```
   - Or use GitHub Actions to deploy from repo to Function App (see CI/CD section).

4. Ensure the Function has an Event Hub trigger bound to the correct Event Hub name/consumer group.

5. Function logic should:
   - Deserialize incoming event JSON
   - Validate/transform fields
   - Upsert into Cosmos DB container with partition key `listingId` (or chosen key)
   - Log telemetry to Application Insights

---

## 7. Ingest sample data
1. Use the producer script in this repo:
   ```bash
   cd producer
   # install deps if required
   python producer.py --file ../data/airbnb_sample.csv --connection-string "<EVENTHUB_CONNECTION_STRING>" --eventhub "$EH_NAME"
   ```
   Or:
   ```bash
   node producer/send.js --file ../data/airbnb_sample.json --connectionString "<EVENTHUB_CONNECTION_STRING>"
   ```

2. Confirm events appear in Event Hub (Azure Portal / metrics). The Function should process and write to Cosmos DB.

---

## 8. Validate data in Cosmos DB
- Use Azure Portal > Cosmos DB > Data Explorer to query documents:
  ```sql
  SELECT TOP 10 c.listingId, c.title, c.price, c.updatedAt
  FROM c
  ORDER BY c._ts DESC
  ```
- Or use Azure CLI / SDK to run queries.

---

## 9. Observability and monitoring
- Enable Application Insights for Function App:
  - In Azure Portal or via CLI, link Application Insights instance to the Function App.
- Monitor:
  - Function invocation count, failures, durations
  - Event Hub incoming/outgoing metrics
  - Cosmos DB RU consumption and throttling (429s)
- Logging: structured logs (JSON) and telemetry for errors and payload sampling.

---

## 10. CI/CD (recommended)
Use GitHub Actions to automate:
- Lint, unit tests
- Build and publish function to Azure
- Apply infrastructure changes via bicep/terraform

Example high-level workflow steps:
1. On push to main:
   - Checkout code
   - Install dependencies
   - Run tests
   - Deploy functions using azure/functions-action or Azure CLI
   - Update infra via Terraform/Bicep (if using IaC)

(Include a workflow YAML in `.github/workflows/` tailored to repo runtime.)

---

## 11. Testing
- Unit tests: place under `tests/` and run with pytest/jest/nunit depending on language.
- Integration tests:
  - Use a test Event Hub and Cosmos DB instance (separate RG) to avoid polluting prod.
  - Run producer sending known payloads and assert documents appear in Cosmos DB within expected time.
- End-to-end: run from producer -> Event Hub -> Function -> Cosmos DB and verify results.

Example (Python pytest):
```bash
pip install -r requirements-dev.txt
pytest -q
```

---

## 12. Cost & security considerations
- Cosmos DB RU provisioning affects cost. Start small and autoscale if needed.
- Monitor RU/s and set alerts on high RU or 429 errors.
- Use managed identities (MSI) for Azure Functions to access Cosmos DB where possible.
- Secure Event Hub with Shared Access Policies with minimal privileges for producers/consumers.
- Use private endpoints for Cosmos DB for production security.
- Purge/log retention: consider TTL in Cosmos DB if you have ephemeral events.

---

## 13. Troubleshooting
- No records in Cosmos DB:
  - Check Function logs for exceptions
  - Verify Event Hub connection and consumer group
  - Check if messages are being sent to Event Hub
- Throttled writes (429):
  - Increase RU/s or implement retry/backoff in processing code
- Function cold start / performance:
  - Consider Premium Plan for Functions or use pre-warmed instances
- Authentication errors:
  - Confirm connection strings, keys, and that app settings are configured correctly

---

--

Appendix: Example local.settings.json for Functions (replace values)
```json
{
  "IsEncrypted": false,
  "Values": {
    "AzureWebJobsStorage": "UseDevelopmentStorage=true",
    "FUNCTIONS_WORKER_RUNTIME": "python",
    "EVENTHUB_CONNECTION_STRING": "<EVENTHUB_CONN_STR>",
    "EVENTHUB_NAME": "airbnb-events",
    "COSMOSDB_CONNECTION_STRING": "<COSMOS_CONN_STR>",
    "COSMOSDB_DATABASE": "airbnb",
    "COSMOSDB_CONTAINER": "listings",
    "APPINSIGHTS_INSTRUMENTATIONKEY": "<AI_KEY>"
  }
}
```


Which would you prefer next?

