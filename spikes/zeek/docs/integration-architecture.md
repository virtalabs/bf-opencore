# Integration Architecture (Phase 2.3)

## Data flow options

| Option | Description | Pros | Cons |
|---|---|---|---|
| File polling | Zeek writes JSON logs, Celery beat polls | Simple, matches existing patterns | Latency, file management |
| Named pipe | Zeek streams to pipe, BlueFlow reads | Low latency | Process coupling |
| HTTP push | Zeek POSTs to BlueFlow API via ActiveHTTP | Decoupled | Adds HTTP overhead |
| Message queue | Kafka/Redis between Zeek and BlueFlow | Buffering, reliability | Overkill for small hospitals? |

## Recommendation

TODO: After prototype work.

## Celery task interface

TODO: Sketch how Zeek output feeds into BlueFlow's task system.

## Relationship with active MLLP endpoint (FY2027)

TODO: Can passive-Zeek and active-MLLP share an HL7 parsing layer?
