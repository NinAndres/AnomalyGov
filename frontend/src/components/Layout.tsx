import type { ReactNode } from "react";
import { NavLink, Outlet } from "react-router-dom";

export function Layout() {
  return (
    <div className="app">
      <header className="app-header">
        <div className="brand">
          <span className="brand-name">AnomalyGov</span>
          <span className="brand-tagline">Detecção de anomalias em pagamentos do Poder Executivo Federal</span>
        </div>
        <nav aria-label="Seções">
          <NavLink to="/experimentos">Experimento</NavLink>
          <NavLink to="/exploracao">Exploração</NavLink>
        </nav>
      </header>
      <main className="app-main">
        <Outlet />
      </main>
      <footer className="app-footer">
        Registros sinalizados são <strong>estatisticamente atípicos</strong> e não indicam fraude, irregularidade ou
        ilegalidade. Dados públicos do Portal da Transparência (2025). Nomes e documentos de pessoas físicas não são
        exibidos (LGPD).
      </footer>
    </div>
  );
}

export function Notice({ kind = "info", children }: { kind?: "info" | "warning" | "error"; children: ReactNode }) {
  return (
    <div className={`notice notice-${kind}`} role={kind === "error" ? "alert" : "status"}>
      {children}
    </div>
  );
}

export function Loading({ label = "Carregando…" }: { label?: string }) {
  return (
    <p className="loading" role="status">
      {label}
    </p>
  );
}
