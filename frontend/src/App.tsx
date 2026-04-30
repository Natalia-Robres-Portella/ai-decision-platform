import { Navigate, Route, Routes } from "react-router-dom";
import { Layout } from "./components/Layout";
import { ChatPage } from "./pages/ChatPage";
import { EvalPage } from "./pages/EvalPage";
import { IngestPage } from "./pages/IngestPage";

export default function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route index element={<Navigate to="/chat" replace />} />
        <Route path="/ingest" element={<IngestPage />} />
        <Route path="/chat" element={<ChatPage />} />
        <Route path="/eval" element={<EvalPage />} />
        {/* Catch-all → chat */}
        <Route path="*" element={<Navigate to="/chat" replace />} />
      </Route>
    </Routes>
  );
}
