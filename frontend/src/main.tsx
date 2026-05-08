// Why QueryClientProvider here and not in App?
// React Query's cache is stored in the QueryClient instance. By wrapping at
// the root we guarantee a single shared cache for the entire app. Any component
// in the tree can call useQuery/useMutation without extra setup.
//
// Why BrowserRouter here and not in App?
// BrowserRouter provides the routing context that <Routes>, <NavLink>, and
// <Navigate> depend on. It must wrap the component tree that uses them.
// Keeping providers at main.tsx keeps App.tsx focused on route structure.

import React from "react";
import ReactDOM from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter } from "react-router-dom";
import App from "./App.tsx";
import "./index.css";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      // Don't refetch when the user switches browser tabs — the data
      // doesn't change that fast in a RAG system.
      refetchOnWindowFocus: false,
      // Retry once on failure before showing an error state.
      retry: 1,
      // Data is fresh for 30 s; after that React Query will refetch
      // in the background when the component re-mounts.
      staleTime: 30_000,
    },
  },
});

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <App />
      </BrowserRouter>
    </QueryClientProvider>
  </React.StrictMode>
);
