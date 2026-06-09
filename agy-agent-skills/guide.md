# Antigravity CLI, Google Cloud managed MCP server, skills, agents

1. Install Antigravity CLI & Antigravity 2.0
1. Login (Antigravity Business)
1. Configure Firestore remote MCP server (https://docs.cloud.google.com/firestore/native/docs/use-firestore-mcp) and configure in Antigravity (~/.gemini/config/mcp_config.json). Use "google_credentials" to use Google Application Default Credentials (ADC) 
    {
        "mcpServers": {
            "google-cloud-firestore": {
            "authProviderType": "google_credentials",
            "serverUrl": "https://firestore.googleapis.com/mcp"
            }
        }
    }

1. Start Antigravity CLI using `agy`
1. Run command `/mcp` to view the configured MCP servers and status. Exit the MCP view using `esc`
1. List all Firestore DBs running `list all firestore dbs`. Agy will use the Firestore MCP to list all DBs. Approve tool use. You should see at least one DB (`(default)`)

## Create a new skill
1. In AGY, start with `help me create a skill`
1. Use AGY's `/grill-me` comamnd with the skill description below. Answer additional AGY questions to refine the skill. 
 screen
```md
SKILL METADATA:
- Name: smart-events-admin
- Location: placed in my workspace under './.agents/skills/{skill_name}'.
- Components: SKILL.md (Core guidelines, instructions, and standard Firestore workflows for
the agent)

GOAL:
CRUD operations for an event system backend (stored in Google Cloud Firestore). The event data is stored in Firestore DB `smart-events`. Collection `_metadata` contains document `global` which contains the metadata of all relevent event data (incl. field and json schemas, defintion and description of available Firestore collections, sample documents, etc)

CONSTRAINTS:
- Only use MCP server 'google-cloud-firestore' when interacting with Google Firestore!
- Only operate on Firestore DB `smart-events`.
- Read the data metadata the `global` document in `_metadata` collection to understand the data structure of DB `smart-events` and where to find what information.
```
1. Use `/skills` and find the newly created skill 'smart-events-admin'.
1. Ran a couple of queries. E.g.
   - explicit skill usage: `/smart-events-admin list all events``
   - implicit skills usage: `show me all sessions of the smart events event but only for day 1`
    > agy will likely create a python script (or similar) to process/filter the returned Firestore docs (to return day 1 sessions only)

## Create an ADK agent using agents-cli and run it locally.

1. Ensure [agents-cli](https://google.github.io/agents-cli/) is installed.
    > once installed you'll see a set of skills starting with 'google-agents-cli...' in agy
1. Use the `/planning` command to enable agy's planning mode.
1. Use the prompt below to create a code first ADK agent that uses the `smart-events-admin` skill

```md
GOAL:
Create a new ADK agent that uses the 'smart-events-admin' skill to enable users to interact with smart events data. 

CONSTRAINTS:
- The agent code is stored in folder './src'
- Use Google Cloud Application Default Credentials for any interaction with Google Cloud services (like managed MCP servers)
```
1. inspect the implementaion plan using `/artifact` and then open. Feel free to place comments asking agy to provide updates to the implementation plan. Once review is finished then approve the plan.
1. Next (once done) I want to test the agent locally. `start the agent locally so i can test it in a playground`.
    > the ADK playground is started (http://127.0.0.1:8085). use the browser to naviate to that URL.
    > test a couple of queries (like 'list the events' or 'how many sessions are registered for event smart events 2026)

1. Agy starts a sub task (agent) for this long running operation. Inspect the task list using `/tasks`

## Deploy the agent to Google Cloud
1. in agy run `deploy the agent to google cloud`.
    > This starts a long running task again (having agy to regularily check the status). Since this a background operation you can continue to interact with agy
    > agy likely hits some issues (permission/access issues as the used Agent Runtime service likely won't have the necessary permissions) - agy will try to figure out the issue if you give it the right permissions (tool calling)
1. once deployment has finished you let's get the deployment details `show me the details of the deployed agent`
    > The output contains the playground URL of the deployed agent. Open the URL and interact with the deployed agent.
    > Also inspect the deployment's trace information (it might take a couple of minutes until session/trace information shows up)

1. Once done. You can now ask what agy learned and how to improve the prompt to avoid and pitfalls in future. E.g. you can ask 

```md
Based on what you learned (access/identity issues) how can i improve the prompt to trigger the deployment "deploy the agent to google cloud". Ideally I want to avoid hitting any issues during or after deployment.
```

## Publish the agent to Gemini Enterprise
1. make the agent available to end users via publshing to Gemini Enterpri. run `publish the agent to gemini enterprise`.
1. Once finished. Navigate to the Gemini Enterprise instance and interact with your agent.