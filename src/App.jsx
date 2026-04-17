import { useEffect, useRef, useState } from "react";

const POLL_MS = 1000;
const TOKEN_BADGE_MS = 6000;

const EMPTY_STATE = {
  connectionKind: "waiting",
  connectionText: "Connecting...",
  clock: "--:--:--",
  tokenBadgeVisible: false,
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
  return `${Math.max(0, Math.floor(Number(value)))}s`;
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

function looksCloudy(conditionText) {
  const text = String(conditionText ?? "").toLowerCase();
  const markers = ["cloud", "overcast", "nuvol", "coperto", "mist", "fog", "haze"];
  return markers.some((marker) => text.includes(marker));
}

function metricRows(rows) {
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

function DetailCard({ title, rows }) {
  return (
    <article className="detail-card">
      <div className="detail-card-head">
        <p className="detail-card-title">{title}</p>
      </div>
      {metricRows(rows)}
    </article>
  );
}

function EnergyGlyph({ kind }) {
  if (kind === "sun") {
    return (
      <svg viewBox="0 0 48 48" className="glyph">
        <circle cx="24" cy="24" r="8" />
        <g>
          <line x1="24" y1="4" x2="24" y2="12" />
          <line x1="24" y1="36" x2="24" y2="44" />
          <line x1="4" y1="24" x2="12" y2="24" />
          <line x1="36" y1="24" x2="44" y2="24" />
          <line x1="10" y1="10" x2="15" y2="15" />
          <line x1="33" y1="33" x2="38" y2="38" />
          <line x1="10" y1="38" x2="15" y2="33" />
          <line x1="33" y1="15" x2="38" y2="10" />
        </g>
      </svg>
    );
  }

  if (kind === "moon") {
    return (
      <svg viewBox="0 0 48 48" className="glyph">
        <path d="M31 8c-8 2-13 9-11 17s10 13 18 11c-3 2-7 4-12 4-10 0-18-8-18-18 0-8 5-15 12-18 3-1 7-1 11 0z" />
      </svg>
    );
  }

  if (kind === "clouds") {
    return (
      <svg viewBox="0 0 48 48" className="glyph glyph-clouds">
        <path d="M14 33h18a7 7 0 0 0 0-14 10 10 0 0 0-19-2A7 7 0 0 0 14 33z" />
      </svg>
    );
  }

  if (kind === "solar") {
    return (
      <svg viewBox="0 0 48 48" className="glyph">
        <path d="M10 14h28l-3 18H13z" />
        <path d="M16 14l4-6h8l4 6" />
        <line x1="18" y1="19" x2="18" y2="30" />
        <line x1="24" y1="19" x2="24" y2="30" />
        <line x1="30" y1="19" x2="30" y2="30" />
        <line x1="14" y1="24" x2="34" y2="24" />
      </svg>
    );
  }

  if (kind === "home") {
    return (
      <svg viewBox="0 0 48 48" className="glyph">
        <path d="M8 22L24 10l16 12" />
        <path d="M14 20v18h20V20" />
        <path d="M21 38V28h6v10" />
      </svg>
    );
  }

  if (kind === "grid") {
    return (
      <svg viewBox="0 0 48 48" className="glyph">
        <path d="M24 8l8 10h-5l5 8h-5l4 14H17l4-14h-5l5-8h-5z" />
      </svg>
    );
  }

  return (
    <svg viewBox="0 0 48 48" className="glyph">
      <rect x="12" y="14" width="24" height="20" rx="4" />
      <rect x="36" y="20" width="4" height="8" rx="2" />
      <line x1="17" y1="24" x2="24" y2="24" />
      <line x1="28" y1="24" x2="31" y2="24" />
      <line x1="29.5" y1="22.5" x2="29.5" y2="25.5" />
    </svg>
  );
}

function FlowLine({ className, active, reverse = false, tone = "solar", path }) {
  return (
    <g className={`flow-group ${className} tone-${tone} ${active ? "is-active" : ""} ${reverse ? "is-reverse" : ""}`}>
      <path className="flow-track" d={path} pathLength="100" />
      {active ? (
        <>
          <circle className="flow-orb flow-orb-core" r="4.5">
            <animateMotion dur="4.8s" repeatCount="indefinite" path={path} rotate="auto" />
          </circle>
          <circle className="flow-orb flow-orb-aura" r="9">
            <animateMotion dur="4.8s" repeatCount="indefinite" path={path} rotate="auto" />
          </circle>
          <circle className="flow-orb flow-orb-core delay-1" r="4.5">
            <animateMotion dur="4.8s" begin="1.6s" repeatCount="indefinite" path={path} rotate="auto" />
          </circle>
          <circle className="flow-orb flow-orb-aura delay-1" r="9">
            <animateMotion dur="4.8s" begin="1.6s" repeatCount="indefinite" path={path} rotate="auto" />
          </circle>
          <circle className="flow-orb flow-orb-core delay-2" r="4.5">
            <animateMotion dur="4.8s" begin="3.2s" repeatCount="indefinite" path={path} rotate="auto" />
          </circle>
          <circle className="flow-orb flow-orb-aura delay-2" r="9">
            <animateMotion dur="4.8s" begin="3.2s" repeatCount="indefinite" path={path} rotate="auto" />
          </circle>
        </>
      ) : null}
    </g>
  );
}

function EnergyNode({ className, kind, label, value, accent = "neutral", center = false, subtitle = null }) {
  return (
    <div className={`energy-node ${className} accent-${accent} ${center ? "energy-node-center" : ""}`}>
      <div className="energy-icon-wrap">
        {center ? <span className="home-ring ring-a" /> : null}
        {center ? <span className="home-ring ring-b" /> : null}
        <div className="energy-icon"><EnergyGlyph kind={kind} /></div>
      </div>
      <div className="energy-copy">
        <p className="energy-label">{label}</p>
        <p className="energy-value">{value}</p>
        {subtitle ? <p className="energy-subtitle">{subtitle}</p> : null}
      </div>
    </div>
  );
}

function EnergyFlowCard({ realtime, battery, grid, inverter, weather }) {
  const pvPower = Number(realtime.pv_power_watts ?? 0);
  const gridPower = Number(grid.power_watts ?? 0);
  const batteryPower = Math.abs(Number(battery.power_watts ?? 0));
  const batteryMode = battery.mode_label ?? "Standby";
  const currentHour = new Date().getHours();
  const isNight = currentHour < 6 || currentHour >= 20;
  const cloudy = looksCloudy(weather?.today_text);

  const importing = gridPower < 0 ? Math.abs(gridPower) : 0;
  const exporting = gridPower > 0 ? gridPower : 0;
  const charging = batteryMode === "Charging" ? batteryPower : 0;
  const discharging = batteryMode === "Discharging" ? batteryPower : 0;
  const houseConsumption = Math.max(0, pvPower + importing + discharging - exporting - charging);
  const gridModeText = importing > 0 ? `Import ${formatWatts(importing)}` : exporting > 0 ? `Export ${formatWatts(exporting)}` : "Balanced";

  return (
    <section className="panel flow-panel">
      <div className="panel-header panel-header-strong">
        <div>
          <p className="eyebrow">Energy Distribution</p>
          <h2 className="flow-title">Live Energy Overview</h2>
        </div>
        <div className="flow-legend">
          <span className="legend-dot solar" /> Live flow
        </div>
      </div>

      <div className="flow-summary">
        <div className="summary-chip">
          <span>House Load</span>
          <strong>{formatWatts(houseConsumption)}</strong>
        </div>
        <div className="summary-chip">
          <span>Battery</span>
          <strong>{formatPercent(battery.soc_percent)} · {batteryMode}</strong>
        </div>
        <div className="summary-chip">
          <span>Grid</span>
          <strong>{importing > 0 ? `Import ${formatWatts(importing)}` : exporting > 0 ? `Export ${formatWatts(exporting)}` : "Balanced"}</strong>
        </div>
      </div>

      <div className="energy-flow">
        <svg className="flow-svg" viewBox="0 0 1200 470" preserveAspectRatio="none" aria-hidden="true">
          <FlowLine
            className="solar-to-home"
            active={pvPower > 0 && houseConsumption > 0}
            tone="solar"
            path="M 296 200 L 475 200"
          />
          <FlowLine
            className="solar-to-battery"
            active={charging > 0}
            tone="battery"
            path="M 184 248 L 184 292 Q 184 312 204 312 L 296 312 Q 316 312 316 332 L 316 376"
          />
          <FlowLine
            className="battery-to-home"
            active={discharging > 0}
            tone="battery"
            path="M 408 248 L 500 248 Q 520 248 520 228 L 520 220 Q 520 200 500 200 L 475 200"
          />
          <FlowLine
            className="grid-import"
            active={importing > 0}
            tone="import"
            reverse
            path="M 926 200 L 725 200"
          />
          <FlowLine
            className="grid-export"
            active={exporting > 0}
            tone="export"
            path="M 725 200 L 926 200"
          />
        </svg>

        <div className={`sun-source ${isNight ? "is-night" : "is-day"}`}>
          <div className="sun-radiance sun-radiance-a" />
          <div className="sun-radiance sun-radiance-b" />
          <div className="sun-core-wrap">
            <div className="sun-core">
              <EnergyGlyph kind={isNight ? "moon" : "sun"} />
              {cloudy ? (
                <div className="sky-clouds">
                  <EnergyGlyph kind="clouds" />
                </div>
              ) : null}
            </div>
            <p className="sun-label">{isNight ? "Moon" : "Sun"}</p>
            {pvPower > 0 ? <p className="sun-value">Generating</p> : null}
          </div>
        </div>
        <EnergyNode className="node-solar" kind="solar" label="Solar" value={formatWatts(pvPower)} accent="solar" subtitle="Panel production" />
        <EnergyNode className="node-home" kind="home" label="Home" value={formatWatts(houseConsumption)} accent="home" center subtitle="Instant consumption" />
        <EnergyNode
          className="node-grid"
          kind="grid"
          label="Grid"
          value={importing > 0 ? `↓ ${formatWatts(importing)}` : exporting > 0 ? `↑ ${formatWatts(exporting)}` : "0 W"}
          accent={importing > 0 ? "import" : exporting > 0 ? "export" : "grid"}
          subtitle={gridModeText}
        />
        <EnergyNode
          className="node-battery"
          kind="battery"
          label="Battery"
          value={`${formatPercent(battery.soc_percent)} · ${batteryMode === "Standby" ? "Idle" : formatWatts(batteryPower)}`}
          accent="battery"
          subtitle={batteryMode}
        />
      </div>

      <div className="flow-footer">
        <div className="footer-chip">
          <span>PV1</span>
          <strong>{formatVolts(inverter.pv1_voltage_volts)} / {formatAmps(inverter.pv1_current_amps)}</strong>
        </div>
        <div className="footer-chip">
          <span>PV2</span>
          <strong>{formatVolts(inverter.pv2_voltage_volts)} / {formatAmps(inverter.pv2_current_amps)}</strong>
        </div>
        <div className="footer-chip">
          <span>Inverter Temp</span>
          <strong>{Number(inverter.temperature_celsius ?? 0).toFixed(1)} °C</strong>
        </div>
      </div>
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

  const detailSections = [
    {
      title: "Plant",
      rows: [
        { label: "Name", value: plant.name ?? "--" },
        { label: "Address", value: plant.address ?? "--" },
        { label: "Online Since", value: plant.turn_on_time ?? "--" },
        { label: "Last Refresh", value: inverter.last_refresh_time ?? "--" }
      ]
    },
    {
      title: "Battery",
      rows: [
        { label: "SOC", value: formatPercent(battery.soc_percent) },
        { label: "Voltage", value: formatVolts(battery.voltage_volts) },
        { label: "Current", value: formatAmps(battery.current_amps) },
        { label: "Mode", value: battery.mode_label ?? "--" }
      ]
    },
    {
      title: "Grid",
      rows: [
        { label: "Power", value: formatWatts(grid.power_watts) },
        { label: "Voltage", value: formatVolts(grid.voltage_volts) },
        { label: "Frequency", value: formatHertz(grid.frequency_hz) },
        { label: "Runtime", value: formatHours(totals.runtime_hours) }
      ]
    },
    {
      title: "Production",
      rows: [
        { label: "Now", value: formatWatts(realtime.pv_power_watts) },
        { label: "Today", value: formatKwh(realtime.today_kwh) },
        { label: "Month", value: formatKwh(realtime.month_kwh) },
        { label: "Total", value: formatKwh(realtime.total_kwh) }
      ]
    },
    {
      title: "Energy Counters",
      rows: [
        { label: "Grid Bought", value: formatKwh(totals.grid_buy_kwh) },
        { label: "Grid Sold", value: formatKwh(totals.grid_sell_kwh) },
        { label: "Battery Charged", value: formatKwh(totals.battery_charge_kwh) },
        { label: "Battery Discharged", value: formatKwh(totals.battery_discharge_kwh) }
      ]
    },
    {
      title: "Weather & Stats",
      rows: [
        { label: "Today", value: weather.today_text ?? "--" },
        { label: "Tomorrow", value: weather.tomorrow_text ?? "--" },
        { label: "Self-use", value: formatPercent(stats.self_use_rate_percent) },
        { label: "Contribution", value: formatPercent(stats.contributing_rate_percent) }
      ]
    },
    {
      title: "Backend",
      rows: [
        { label: "Session Age", value: formatSeconds(status.token_age_seconds) },
        { label: "Refreshes", value: `${status.token_refresh_count ?? "--"}` },
        { label: "Last Success", value: formatEpoch(status.last_success_at) },
        { label: "Last Error", value: viewState.errorMessage }
      ]
    },
    {
      title: "Strings",
      rows: [
        { label: "PV1", value: `${formatVolts(inverter.pv1_voltage_volts)} / ${formatAmps(inverter.pv1_current_amps)}` },
        { label: "PV2", value: `${formatVolts(inverter.pv2_voltage_volts)} / ${formatAmps(inverter.pv2_current_amps)}` },
        { label: "Temp", value: `${Number(inverter.temperature_celsius ?? 0).toFixed(1)} °C` },
        { label: "API Base", value: status.api_base ?? "--" }
      ]
    }
  ];

  return (
    <main className="shell">
      <section className="hero hero-ha">
        <div className="hero-copy">
          <p className="eyebrow">Viessmann Solar</p>
          <h1>Energy dashboard</h1>
          <p className="hero-subtitle">{plant.name ?? "Solar monitor"} · {plant.address ?? "Realtime snapshot"}</p>
        </div>
        <div className="hero-meta">
          <span className={`pill pill-accent ${viewState.tokenBadgeVisible ? "" : "is-hidden"}`}>Token renewed</span>
          <span className={`pill pill-${viewState.connectionKind}`}>{viewState.connectionText}</span>
          <span className="clock">{viewState.clock}</span>
        </div>
      </section>

      <section className="kpi-strip">
        <div className="kpi-pill">
          <span>Solar</span>
          <strong>{formatWatts(realtime.pv_power_watts)}</strong>
        </div>
        <div className="kpi-pill">
          <span>House</span>
          <strong>{formatWatts(Math.max(0, Number(realtime.pv_power_watts ?? 0) + Math.max(0, -Number(grid.power_watts ?? 0)) + (battery.mode_label === "Discharging" ? Math.abs(Number(battery.power_watts ?? 0)) : 0) - Math.max(0, Number(grid.power_watts ?? 0)) - (battery.mode_label === "Charging" ? Math.abs(Number(battery.power_watts ?? 0)) : 0)))}</strong>
        </div>
        <div className="kpi-pill">
          <span>Battery</span>
          <strong>{formatPercent(battery.soc_percent)}</strong>
        </div>
        <div className="kpi-pill">
          <span>Grid</span>
          <strong>{formatWatts(grid.power_watts)}</strong>
        </div>
      </section>

      <EnergyFlowCard realtime={realtime} battery={battery} grid={grid} inverter={inverter} weather={weather} />

      <section className="detail-grid">
        {detailSections.map((section) => (
          <DetailCard key={section.title} title={section.title} rows={section.rows} />
        ))}
      </section>
    </main>
  );
}
