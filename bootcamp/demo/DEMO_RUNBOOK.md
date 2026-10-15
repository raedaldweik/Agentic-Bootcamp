# Live demo runbook: "Build a population-health agent", end to end on SAS Viya

One conversation with the **Population Health Builder** agent in RAM (`../agents/population_health_builder_demo.md`),
SAS Viya open on the second screen. The audience watches a table, a model and a decision appear in
Viya as the agent makes them. About 15 minutes.

## The day before

1. **Tool server.** The RAM template for the SAS MCP server with `MCP_TIERS=0,1,2,5,6,7`
   (tier 7 is Intelligent Decisioning), one instance for the presenter.
2. **Rights.** The client the instance signs in with needs Business Rules, Intelligent Decisioning
   and Model Publish, on top of the compute context, `Public` and Model Studio:
   `python verify_team_client.py --client-id <id> --client-secret <secret> --write --automl --decisioning`
   must be all PASS.
3. **The agent.** Create `Population Health Builder` in RAM with the prompt and the 32 tools from
   `../tools.md`.
4. **Rehearse the whole conversation once**, with the five messages below, but with the suffix
   `_REHEARSAL` instead of `_DEMO` (say so in the first message: "use the suffix REHEARSAL"). Note
   the model module id and the decision module id it reports and put them into the prompt as
   `<<REHEARSAL_MODEL>>` and `<<REHEARSAL_DECISION>>`. Those are the fallback if AutoML is slow or
   publishing fails on the day. Do not delete them.
5. **Viya tabs open and signed in**, in this order: SAS Data Explorer (Manage Data), Model Studio,
   Model Manager, Intelligent Decisioning. Zoom the browser to 125%.

## The script

| Minute | You type | The agent does | You show in Viya |
|---|---|---|---|
| 0 | `Hi, we want to build a population-health agent for people with diabetes who are at risk of getting worse. Can you build it for us?` | Restates the idea, names the decision, lists data, model, decision, agent. Asks to start. | Nothing yet. Say: "four steps, and you will see each one appear in Viya." |
| 1 | `Yes, start with the data.` | Creates `Public.PH_DEMO_PATIENTS`, 4,000 rows, profiles it. | Data Explorer, cas-shared-default, Public: refresh, open the table, show the columns and a few rows. Point at `deterioration_next_12m`. |
| 3 | `Now train the model.` | Makes the modelling table, starts AutoML in Model Studio (3 to 6 minutes), then registers, publishes, scores two patients. | Model Studio: the project, the pipelines running. While it runs: "this is AutoML trying several algorithms; the agent will tell us which one won." Then Model Manager: the registered model, publish history. |
| 9 | `Turn the model into a decision: who do we contact first, and how?` | Creates the rule set with four rules, locks it, creates the decision flow, publishes it, scores the same two patients through it. | Intelligent Decisioning: Decisions, open `PH_DEMO_OUTREACH_DECISION`, show the flow; Rule sets, open `PH_DEMO_OUTREACH`, show the four rules. |
| 13 | `Now give us the agent.` | The two registration values, a system prompt, five test questions. | Nothing. Read the first test question and its expected number aloud. |

Optional closer, if there is time: register the Bootcamp MCP with the two values, attach it to a new
agent with the prompt the builder wrote, and ask it the first test question on the Hackathon Agent
tab. That is the full loop, built in a quarter of an hour.

## What makes it convincing

- **Refresh, do not pre-open.** Open the Data Explorer folder before Step 1 so the table is not
  there, then refresh after. Same for the Model Studio project list and the Decisions list.
- **Read the numbers off Viya, not off the chat.** The row count in Data Explorer, the champion's
  statistic in Model Studio, the rule text in Intelligent Decisioning.
- **Two patients, same two everywhere.** The well-controlled one and the poorly-controlled one go
  through the model and then through the decision; the audience sees a probability become an action.

## If something goes wrong

| What | Do |
|---|---|
| AutoML is still running after 6 minutes | Keep talking through Model Studio; at 8 minutes type `Use the rehearsal model for now and carry on with the decision.` The agent switches to `<<REHEARSAL_MODEL>>` and says so. |
| `publish_decision_flow` fails with a code-generation error | Environment-side. Show the decision in the Intelligent Decisioning UI, then type `Use the rehearsal decision for scoring.` |
| A tool returns error 12207 or 12212 | The compute session is being relaunched. Wait 30 seconds, type `try again`. |
| A table or project already exists from an earlier run | Intended. The agent reuses it; say "we built this earlier today, so it reuses it." |
| The agent starts dropping or recreating things | Type `stop, reuse what exists`. |
| RAM says not signed in | The tool server's client token; re-instantiate the tool server. The Viya artefacts are untouched. |

## Tear-down

Nothing is deleted automatically. After the event, drop `PH_DEMO_*` and `PH_REHEARSAL_*` tables,
projects, rule sets, decisions and published modules by hand, or ask the builder to list them and
delete them one by one.
