import * as React from "react";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { LifecycleEntry } from "@/stores/simulation-store";

export default function TimelinePanel({ events }: { events: LifecycleEntry[] }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-lg">Lifecycle Timeline</CardTitle>
      </CardHeader>
      <CardContent className="text-sm">
        <div className="space-y-2 max-h-[360px] overflow-auto pr-1">
          {events.length === 0 ? (
            <div className="text-muted-foreground">No events yet.</div>
          ) : (
            events
              .slice()
              .map((e, idx) => (
                <div key={`${e.event_name}-${e.timestamp ?? idx}-${idx}`} className="rounded-md border bg-card p-2">
                  <div className="flex items-baseline justify-between gap-2">
                    <div className="font-medium">{e.event_name}</div>
                    <div className="text-xs text-muted-foreground">
                      {e.timestamp ? e.timestamp.slice(11, 19) : ""}
                    </div>
                  </div>
                  {e.agent_role ? <div className="text-xs text-muted-foreground">{e.agent_role}</div> : null}
                  {e.description ? <div className="text-xs mt-1 text-muted-foreground">{e.description}</div> : null}
                </div>
              ))
          )}
        </div>
      </CardContent>
    </Card>
  );
}

