import * as React from "react";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { kmhToMph, kmToMiles } from "@/lib/units";
import type { ActivityEntry } from "@/stores/simulation-store";

const FREEZING_THRESHOLD_F = 36.0;

function TempBadge({ value }: { value?: number }) {
  const bad = typeof value === "number" && value <= FREEZING_THRESHOLD_F;
  const text = typeof value === "number" ? `${value.toFixed(2)}F` : "—";
  return (
    <span className={bad ? "text-destructive font-medium" : "text-emerald-600 font-medium"}>
      {text}
    </span>
  );
}

export default function ActivityLogCard({ steps }: { steps: ActivityEntry[] }) {
  const newestFirst = React.useMemo(() => [...steps].reverse(), [steps]);

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-lg">Simulation Activity</CardTitle>
      </CardHeader>
      <CardContent className="text-sm">
        <div className="space-y-3 max-h-[520px] overflow-auto pr-1">
          {newestFirst.length === 0 ? (
            <div className="text-muted-foreground">No activity yet. Click Start to begin.</div>
          ) : (
            newestFirst.map((s, idx) => {
              const time = s.timestamp ? s.timestamp.slice(11, 19) : "";
              if (s.kind === "telemetry") {
                const bad = typeof s.internal_temp === "number" && s.internal_temp <= FREEZING_THRESHOLD_F;
                const pay = s.payload ?? {};
                const segMi =
                  typeof pay.segment_progress_km === "number" ? kmToMiles(pay.segment_progress_km) : null;
                const remMi =
                  typeof pay.remaining_distance_km === "number" ? kmToMiles(pay.remaining_distance_km) : null;
                const totMi = typeof pay.route_total_km === "number" ? kmToMiles(pay.route_total_km) : null;
                return (
                  <div key={`telemetry-${s.timestamp ?? "t"}-${idx}`} className="rounded-md border bg-card p-3">
                    <div className="flex items-baseline justify-between gap-2">
                      <div className="font-medium">Telemetry tick</div>
                      <div className="text-xs text-muted-foreground">{time}</div>
                    </div>
                    <div className="mt-2 text-xs text-muted-foreground">
                      Route: <span className="text-foreground">{s.route_segment ?? "—"}</span>
                    </div>
                    <div className="mt-1 text-xs text-muted-foreground">
                      Location:{" "}
                      <span className="text-foreground">
                        {s.lat.toFixed(6)}, {s.lng.toFixed(6)}
                      </span>
                    </div>
                    <div className="mt-2 flex flex-wrap gap-3">
                      <div>
                        <div className="text-xs text-muted-foreground">Internal Temp</div>
                        <TempBadge value={s.internal_temp} />
                        {typeof s.internal_temp === "number" ? (
                          <div className="text-xs text-muted-foreground">
                            {bad ? "Status: VIOLATED" : "Status: OK"}
                          </div>
                        ) : null}
                      </div>
                      <div>
                        <div className="text-xs text-muted-foreground">External Temp</div>
                        <TempBadge value={s.external_temp} />
                      </div>
                      <div>
                        <div className="text-xs text-muted-foreground">Weather</div>
                        <div className="text-foreground">{s.weather_state ?? "—"}</div>
                      </div>
                      <div>
                        <div className="text-xs text-muted-foreground">Risk</div>
                        <div className="text-foreground">{typeof s.risk_level === "number" ? s.risk_level.toFixed(2) : "—"}</div>
                      </div>
                      <div>
                        <div className="text-xs text-muted-foreground">Speed</div>
                        <div className="text-foreground">
                          {typeof s.speed === "number" ? `${kmhToMph(s.speed).toFixed(1)} mph` : "—"}
                        </div>
                      </div>
                      <div>
                        <div className="text-xs text-muted-foreground">Heading</div>
                        <div className="text-foreground">{typeof s.heading === "number" ? `${s.heading.toFixed(0)}°` : "—"}</div>
                      </div>
                      <div>
                        <div className="text-xs text-muted-foreground">Progress</div>
                        <div className="text-foreground">
                          {typeof pay.progress_pct === "number" ? `${Number(pay.progress_pct).toFixed(1)}%` : "—"}
                        </div>
                      </div>
                      {segMi !== null ? (
                        <div>
                          <div className="text-xs text-muted-foreground">Segment progress</div>
                          <div className="text-foreground">{segMi.toFixed(2)} mi</div>
                        </div>
                      ) : null}
                      {remMi !== null ? (
                        <div>
                          <div className="text-xs text-muted-foreground">Remaining</div>
                          <div className="text-foreground">{remMi.toFixed(2)} mi</div>
                        </div>
                      ) : null}
                      {totMi !== null ? (
                        <div>
                          <div className="text-xs text-muted-foreground">Route total</div>
                          <div className="text-foreground">{totMi.toFixed(2)} mi</div>
                        </div>
                      ) : null}
                    </div>
                  </div>
                );
              }

              const payload = s.payload ?? {};
              const reasoningTrace =
                typeof payload.reasoning_trace === "string" && payload.reasoning_trace ? payload.reasoning_trace : null;
              const decisionReason =
                typeof payload.decision_reason === "string" && payload.decision_reason ? payload.decision_reason : null;
              const llmPrompt = typeof payload.llm_prompt === "string" && payload.llm_prompt ? payload.llm_prompt : null;
              const llmResponse = typeof payload.llm_response === "string" && payload.llm_response ? payload.llm_response : null;
              const warehouseName =
                payload?.warehouse_candidate?.name && typeof payload.warehouse_candidate.name === "string"
                  ? payload.warehouse_candidate.name
                  : null;

              return (
                <div key={`lifecycle-${s.timestamp ?? "l"}-${s.event_name}-${idx}`} className="rounded-md border bg-card p-3">
                  <div className="flex items-baseline justify-between gap-2">
                    <div className="font-medium">{s.event_name}</div>
                    <div className="text-xs text-muted-foreground">{time}</div>
                  </div>
                  {s.agent_role ? <div className="text-xs text-muted-foreground mt-1">{s.agent_role}</div> : null}
                  {s.description ? <div className="text-xs mt-2 text-muted-foreground">{s.description}</div> : null}
                  {warehouseName ? (
                    <div className="text-xs text-muted-foreground mt-2">
                      Warehouse: <span className="text-foreground">{warehouseName}</span>
                    </div>
                  ) : null}
                  {reasoningTrace ? (
                    <div className="mt-2 rounded border bg-muted/30 p-2 text-xs text-foreground whitespace-pre-wrap">
                      {reasoningTrace}
                    </div>
                  ) : null}
                  {decisionReason ? (
                    <div className="mt-2 rounded border bg-muted/30 p-2 text-xs text-foreground whitespace-pre-wrap">
                      {decisionReason}
                    </div>
                  ) : null}
                  {llmPrompt ? (
                    <details className="mt-2">
                      <summary className="cursor-pointer text-xs text-muted-foreground">LLM Prompt</summary>
                      <pre className="mt-1 text-[11px] whitespace-pre-wrap rounded bg-muted/30 p-2 text-foreground">
                        {llmPrompt}
                      </pre>
                    </details>
                  ) : null}
                  {llmResponse ? (
                    <details className="mt-2">
                      <summary className="cursor-pointer text-xs text-muted-foreground">LLM Response</summary>
                      <pre className="mt-1 text-[11px] whitespace-pre-wrap rounded bg-muted/30 p-2 text-foreground">
                        {llmResponse}
                      </pre>
                    </details>
                  ) : null}
                </div>
              );
            })
          )}
        </div>
      </CardContent>
    </Card>
  );
}

