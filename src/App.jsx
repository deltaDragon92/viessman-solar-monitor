import { useEffect, useRef, useState } from "react";

const POLL_MS = 1000;
const TOKEN_BADGE_MS = 6000;

const EMPTY_STATE = {
  connectionKind: "waiting",
  connectionText: "Connecting...",
  clock: "--:--:--",
  tokenBadgeVisible: false,
  tokenBadgeText: "Token renewed",
  data: null,
  errorMessage: "None"
};

function formatWatts(value) {
  return `${Number(value ?? 0).toFixed(0)} W`;
}

function formatKwh(value) {
  return `${Number(value ?? 0).toFixed(2)} kWh`;
}

function formatPercent(value) {
  return `${Number(value ?? 0).toFixed(0)}%`;
}

function formatSeconds(value) {
  if (value == null) return "--";
  const seconds = Math.max(0, Math.floor(Number(value)));
  return `${seconds}s`;
}

function formatEpoch(value) {
  if (!value) return "--";
  return new Date(Number(value) * 1000).toLocaleTimeString();
}

function formatVolts(value) {
  return `${Number(value ?? 0).toFixed(1)} V`;
}

function formatAmps(value) {
  return `${Number(value ?? 0).toFixed(1)} A`;
}

function formatHertz(value) {
  return `${Number(value ?? 0).toFixed(2)} Hz`;
}

function formatHours(value) {
  return `${Number(value ?? 0).toFixed(0)} h`;
}

function MetricCard({ label, value, hint }) {
  return (
    <article className="panel stat-panel">
      <p className="label">{label}</p>
      <p className="value">{value}</p>
      <p className="hint">{hint}</p>
    </article>
  );
}

function DetailRows({ rows }) {
  return (
    <dl className="details compact-details">
      {rows.map((row) => (
        <div key={row.label}>
          <dt>{row.label}</dt>
          <dd>{row.value}</dd>
        </div>
      ))}
    </dl>
  );
}

function SectionCard({ title, rows }) {
  return (
    <section className="overview-card">
      <p className="label">{title}</p>
      <DetailRows rows={rows} />
    </section>
  );
}

export default function App() {
  const [viewState, setViewState] = useState(EMPTY_STATE);
  const lastTokenRefreshCount = useRef(null);
  const tokenBadgeTimeout = useRef(null);

  useEffect(() => {
    let disposed = false;

    async function fetchSnapshot() {
      try {
        const response = await fetch("/api/snapshot", { cache: "no-store" });
        const payload = await response.json();

        if (!response.ok || !payload.ok || !payload.snapshot) {
          throw new Error(payload.backend?.last_error ?? payload.error ?? "Backend unavailable");
        }

        if (disposed) return;

        const tokenRefreshCount = payload.backend.client_status.token_refresh_count;
        const shouldShowTokenBadge =
          lastTokenRefreshCount.current !== null &&
          tokenRefreshCount > lastTokenRefreshCount.current;

        lastTokenRefreshCount.current = tokenRefreshCount;

        setViewState((previous) => ({
          ...previous,
          connectionKind: "ok",
          connectionText: "Live",
          clock: new Date().toLocaleTimeString(),
          tokenBadgeVisible: shouldShowTokenBadge ? true : previous.tokenBadgeVisible,
          data: payload,
          errorMessage: payload.backend.last_error ?? "None"
        }));

        if (shouldShowTokenBadge) {
          clearTimeout(tokenBadgeTimeout.current);
          tokenBadgeTimeout.current = setTimeout(() => {
            setViewState((previous) => ({ ...previous, tokenBadgeVisible: false }));
          }, TOKEN_BADGE_MS);
        }
      } catch (error) {
        const fallbackMessage = error instanceof Error ? error.message : String(error);

        try {
          const statusResponse = await fetch("/api/status", { cache: "no-store" });
          const statusPayload = await statusResponse.json();

          if (disposed) return;

          const lastError = statusPayload.backend?.last_error ?? fallbackMessage;
          const retryDelay = statusPayload.backend?.next_retry_delay_seconds;
          setViewState((previous) => ({
            ...previous,
            connectionKind: "error",
            connectionText: "Offline",
            clock: new Date().toLocaleTimeString(),
            errorMessage:
              retryDelay == null ? lastError : `${lastError} (retry in ${retryDelay}s)`
          }));
        } catch {
          if (disposed) return;
          setViewState((previous) => ({
            ...previous,
            connectionKind: "error",
            connectionText: "Offline",
            clock: new Date().toLocaleTimeString(),
            errorMessage: fallbackMessage
          }));
        }
      }
    }

    fetchSnapshot();
    const intervalId = window.setInterval(fetchSnapshot, POLL_MS);

    return () => {
      disposed = true;
      window.clearInterval(intervalId);
      clearTimeout(tokenBadgeTimeout.current);
    };
  }, []);

  const snapshot = viewState.data?.snapshot ?? {};
  const backend = viewState.data?.backend ?? {};
  const status = backend.client_status ?? {};
  const plant = snapshot.plant ?? {};
  const realtime = snapshot.realtime ?? {};
  const battery = snapshot.battery ?? {};
  const grid = snapshot.grid ?? {};
  const totals = snapshot.totals ?? {};
  const inverter = snapshot.inverter ?? {};
  const stats = snapshot.stats ?? {};
  const weather = snapshot.weather ?? {};

  const batteryRows = [
    { label: "Voltage", value: formatVolts(battery.voltage_volts) },
    { label: "Current", value: formatAmps(battery.current_amps) },
    { label: "Power", value: formatWatts(battery.power_watts) },
    { label: "Mode", value: battery.mode_label ?? "--" }
  ];

  const gridRows = [
    { label: "Voltage", value: formatVolts(grid.voltage_volts) },
    { label: "Frequency", value: formatHertz(grid.frequency_hz) },
    { label: "Power Flow", value: formatWatts(grid.power_watts) },
    { label: "Runtime", value: formatHours(totals.runtime_hours) }
  ];

  const pvRows = [
    {
      label: "PV1",
      value: `${formatVolts(inverter.pv1_voltage_volts)} / ${formatAmps(inverter.pv1_current_amps)}`
    },
    {
      label: "PV2",
      value: `${formatVolts(inverter.pv2_voltage_volts)} / ${formatAmps(inverter.pv2_current_amps)}`
    },
    { label: "Temperature", value: `${Number(inverter.temperature_celsius ?? 0).toFixed(1)} °C` },
    { label: "Total Yield", value: formatKwh(realtime.total_kwh) }
  ];

  const weatherRows = [
    { label: "Today", value: weather.today_text ?? "--" },
    { label: "Tomorrow", value: weather.tomorrow_text ?? "--" },
    { label: "Self-use", value: formatPercent(stats.self_use_rate_percent) },
    { label: "Contribution", value: formatPercent(stats.contributing_rate_percent) }
  ];

  const plantRows = [
    { label: "Name", value: plant.name ?? "--" },
    { label: "Address", value: plant.address ?? "--" },
    { label: "Online Since", value: plant.turn_on_time ?? "--" },
    { label: "Temperature", value: `${Number(inverter.temperature_celsius ?? 0).toFixed(1)} °C` }
  ];

  const productionRows = [
    { label: "Today", value: formatKwh(realtime.today_kwh) },
    { label: "This Month", value: formatKwh(realtime.month_kwh) },
    { label: "Total", value: formatKwh(realtime.total_kwh) },
    { label: "Self-use Rate", value: formatPercent(stats.self_use_rate_percent) }
  ];

  const energyRows = [
    { label: "Grid Bought", value: formatKwh(totals.grid_buy_kwh) },
    { label: "Grid Sold", value: formatKwh(totals.grid_sell_kwh) },
    { label: "Battery Charged", value: formatKwh(totals.battery_charge_kwh) },
    { label: "Battery Discharged", value: formatKwh(totals.battery_discharge_kwh) }
  ];

  const backendRows = [
    { label: "API Base", value: status.api_base ?? "--" },
    { label: "Last Success", value: formatEpoch(status.last_success_at) },
    {
      label: "Poll Interval",
      value: `${backend.poll_interval_seconds ?? "--"}s base / ${backend.next_retry_delay_seconds ?? "--"}s next`
    },
    { label: "Last Error", value: viewState.errorMessage }
  ];

  return (
    <main className="shell">
      <section className="hero">
        <div className="hero-copy">
          <p className="eyebrow">Viessmann Solar</p>
          <h1>Live plant monitor</h1>
        </div>
        <div className="hero-meta">
          <span className={`pill pill-accent ${viewState.tokenBadgeVisible ? "" : "is-hidden"}`}>
            Token renewed
          </span>
          <span className={`pill pill-${viewState.connectionKind}`}>{viewState.connectionText}</span>
          <span className="clock">{viewState.clock}</span>
        </div>
      </section>

      <section className="grid">
        <MetricCard label="PV Power" value={formatWatts(realtime.pv_power_watts)} hint="Instant solar generation" />
        <MetricCard label="Battery" value={formatPercent(battery.soc_percent)} hint={`Mode: ${battery.mode_label ?? "--"}`} />
        <MetricCard label="Grid" value={formatWatts(grid.power_watts)} hint="Positive = export, negative = import" />
        <MetricCard label="Session" value={formatSeconds(status.token_age_seconds)} hint={`Refreshes: ${status.token_refresh_count ?? "--"}`} />
      </section>

      <section className="workspace">
        <article className="panel insights-panel">
          <div className="panel-header">
            <h2>Live Details</h2>
            <span className="microcopy">Real-time electrical overview</span>
          </div>
          <div className="insights-grid">
            <SectionCard title="Battery Detail" rows={batteryRows} />
            <SectionCard title="Grid Detail" rows={gridRows} />
            <SectionCard title="PV Strings" rows={pvRows} />
            <SectionCard title="Weather & Rates" rows={weatherRows} />
          </div>
        </article>

        <article className="panel overview-panel">
          <div className="panel-header">
            <h2>Overview</h2>
            <span className="microcopy">Last refresh: {inverter.last_refresh_time ?? "--"}</span>
          </div>
          <div className="overview-grid">
            <SectionCard title="Plant" rows={plantRows} />
            <SectionCard title="Production" rows={productionRows} />
            <SectionCard title="Energy Counters" rows={energyRows} />
            <SectionCard title="Backend" rows={backendRows} />
          </div>
        </article>
      </section>
    </main>
  );
}
