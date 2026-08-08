import { Routes, Route, Navigate } from "react-router-dom";
import { RequireAuth } from "./components/RequireAuth";
import { RequireResume } from "./components/RequireResume";
import { AppLayout } from "./components/AppLayout";
import { Login } from "./pages/Login";
import { Signup } from "./pages/Signup";
import { Onboarding } from "./pages/Onboarding";
import { Chat } from "./pages/Chat";
import { Saved } from "./pages/Saved";

export function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route path="/signup" element={<Signup />} />
      <Route
        element={
          <RequireAuth>
            <AppLayout />
          </RequireAuth>
        }
      >
        <Route path="/onboarding" element={<Onboarding />} />
        <Route
          path="/"
          element={
            <RequireResume>
              <Chat />
            </RequireResume>
          }
        />
        <Route path="/saved" element={<Saved />} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
