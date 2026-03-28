# UML Sequence Diagram

## Diagram

```mermaid
sequenceDiagram
    actor User
    participant OCR as OpenCode Runtime
    participant OAC as OAC Agent Layer
    participant SP as Superpowers Skills
    participant JCM as jCodeMunch MCP
    participant JDM as jDocMunch MCP
    participant SER as Serena MCP
    participant TST as Test Runner
    participant ART as Artifact Store

    User->>OCR: Submit OC task request
    OCR->>OAC: Route task to active agent

    OAC->>JCM: search_symbols / get_symbol
    JCM-->>OAC: Code retrieval evidence

    OAC->>JDM: search_sections / get_section
    JDM-->>OAC: Documentation retrieval evidence

    OAC->>SP: Validate required skills
    SP-->>OAC: Preflight status

    alt Preflight failed
        OAC->>ART: Write failed preflight artifact
        OAC-->>User: Stop with remediation note
    else Preflight passed
        OAC->>OAC: Execute approval gate
        alt Gate denied
            OAC->>ART: Write gate denial artifact
            OAC-->>User: Stop without edit
        else Gate approved
            OAC->>SER: Apply semantic edit
            SER-->>OAC: Edit status and details

            alt Edit failed
                OAC->>ART: Write edit failure artifact
                OAC-->>User: Stop with edit error
            else Edit succeeded
                OAC->>TST: Run verification command
                TST-->>OAC: Pass/fail result
                OAC->>ART: Publish final workflow artifact
                OAC-->>User: Return completion report
            end
        end
    end
```

## Notes

- Retrieval evidence is mandatory before planning.
- Approval is final authority before edits.
- Artifact publication is required for each stage transition.
