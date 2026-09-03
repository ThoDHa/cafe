import { lazy, Suspense } from "react";
import { BrowserRouter, Route, Routes } from "react-router-dom";
import OrderingPage from "./views/ordering/OrderingPage";

const BaristaPage = lazy(() => import("./views/barista/BaristaPage"));

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<OrderingPage />} />
        <Route
          path="/barista"
          element={
            <Suspense fallback={null}>
              <BaristaPage />
            </Suspense>
          }
        />
      </Routes>
    </BrowserRouter>
  );
}
