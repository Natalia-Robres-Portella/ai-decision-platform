export interface ComponentHealth {
  status: "ok" | "error";
  message: string;
}

export interface HealthStatus {
  status: "ok" | "degraded" | "error";
  version: string;
  components: Record<string, ComponentHealth>;
}
