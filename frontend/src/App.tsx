import { Navigate, Route, Routes } from "react-router-dom";
import { Layout, Notice } from "./components/Layout";
import { ExperimentPage, ExperimentsPage } from "./pages/ExperimentPage";
import { ExplorePage } from "./pages/ExplorePage";
import { JobPage } from "./pages/JobPage";

export function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route index element={<Navigate to="/experimentos" replace />} />
        <Route path="experimentos" element={<ExperimentsPage />} />
        <Route path="experimentos/:name" element={<ExperimentPage />} />
        <Route path="exploracao" element={<ExplorePage />} />
        <Route path="exploracao/jobs/:id" element={<JobPage />} />
        <Route path="*" element={<Notice kind="error">Página não encontrada.</Notice>} />
      </Route>
    </Routes>
  );
}
