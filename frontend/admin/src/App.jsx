import { BrowserRouter, Routes, Route, Navigate, useLocation } from 'react-router-dom';
import Navbar from './components/Navbar';
import ProtectedRoute from './components/ProtectedRoute';
import { ToastProvider } from './components/Toast';
import LoginPage from './pages/LoginPage';
import SubmitPage from './pages/SubmitPage';
import SuccessPage from './pages/SuccessPage';
import GuardsPage from './pages/GuardsPage';
import AdminConstraintsPage from './pages/AdminConstraintsPage';
import WeeksPage from './pages/WeeksPage';
import SubmissionsPage from './pages/SubmissionsPage';
import SettingsPage from './pages/SettingsPage';
import PublishPreviewPage from './pages/PublishPreviewPage';
import ImportConstraintsPage from './pages/ImportConstraintsPage';
import ProfilesPage from './pages/builder/ProfilesPage';
import PositionsPage from './pages/builder/PositionsPage';
import BoardPage from './pages/builder/BoardPage';
import AttendancePage from './pages/AttendancePage';
import AttendanceUserPage from './pages/AttendanceUserPage';
import ActualBoardPage from './pages/ActualBoardPage';
import ReinforcementsReportPage from './pages/ReinforcementsReportPage';
import ProceduresPage from './pages/ProceduresPage';
import ProcedureDetailPage from './pages/ProcedureDetailPage';
import './styles/admin.css';

// Part B (schedule builder + constraints import) is hidden in production via a
// build-time flag. Build with VITE_SCHEDULE_BUILDER_ENABLED=false to drop the
// routes entirely so end users never see that half of the app.
const BUILDER_ENABLED = import.meta.env.VITE_SCHEDULE_BUILDER_ENABLED !== 'false';
// Stage 3 (attendance) — same convention; pairs with backend ATTENDANCE_ENABLED.
const ATTENDANCE_ENABLED = import.meta.env.VITE_ATTENDANCE_ENABLED !== 'false';
// "סידור בפועל" (actual schedule) — same convention; pairs with the backend
// ACTUAL_SCHEDULE_ENABLED comparison-source flag.
const ACTUAL_SCHEDULE_ENABLED = import.meta.env.VITE_ACTUAL_SCHEDULE_ENABLED !== 'false';
// סד"פ (procedure quiz) — DELIBERATE divergence from the flags above: the others
// use `!== 'false'` (default ON), but this feature ships DARK — it defaults OFF
// and is flipped ON only in the final deploy step, once the frontend + bot are
// complete (deploy-safe sequencing: every prior backend step lands in prod with
// this flag unset, so the routes/nav entry are absent for end users).
const PROCEDURES_ENABLED = import.meta.env.VITE_PROCEDURES_ENABLED === 'true';

export default function App() {
  return (
    <BrowserRouter>
      <ToastProvider>
        <AppContent />
      </ToastProvider>
    </BrowserRouter>
  );
}

function AppContent() {
  const location = useLocation();
  const hideNavbar = location.pathname === '/submit' || location.pathname === '/submit/success';

  return (
    <>
      {!hideNavbar && <Navbar />}
      <main className="main-content">
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route path="/submit" element={<SubmitPage />} />
          <Route path="/submit/success" element={<SuccessPage />} />
          <Route path="/guards" element={<ProtectedRoute><GuardsPage /></ProtectedRoute>} />
          <Route path="/guards/:guardId/constraints" element={<ProtectedRoute><AdminConstraintsPage /></ProtectedRoute>} />
          <Route path="/weeks" element={<ProtectedRoute><WeeksPage /></ProtectedRoute>} />
          <Route path="/submissions" element={<ProtectedRoute><SubmissionsPage /></ProtectedRoute>} />
          <Route path="/settings" element={<ProtectedRoute><SettingsPage /></ProtectedRoute>} />
          {/* /export was removed — constraints export is a one-click download on
              each week card (WeekQuickLinks); the page was just a week picker. */}
          <Route path="/publish-preview" element={<ProtectedRoute><PublishPreviewPage /></ProtectedRoute>} />
          {/* Stage 3 — attendance (feature-flagged) */}
          {ATTENDANCE_ENABLED && (
            <>
              <Route path="/attendance" element={<ProtectedRoute><AttendancePage /></ProtectedRoute>} />
              <Route path="/attendance/users/:userId" element={<ProtectedRoute><AttendanceUserPage /></ProtectedRoute>} />
            </>
          )}
          {/* סידור בפועל — the editable execution copy (feature-flagged) */}
          {ACTUAL_SCHEDULE_ENABLED && (
            <>
              <Route path="/actual" element={<ProtectedRoute><ActualBoardPage /></ProtectedRoute>} />
              <Route path="/actual/report" element={<ProtectedRoute><ReinforcementsReportPage /></ProtectedRoute>} />
            </>
          )}
          {/* Part B — constraints import + Schedule Builder (feature-flagged) */}
          {BUILDER_ENABLED && (
            <>
              <Route path="/import" element={<ProtectedRoute><ImportConstraintsPage /></ProtectedRoute>} />
              <Route path="/builder/profiles" element={<ProtectedRoute><ProfilesPage /></ProtectedRoute>} />
              <Route path="/builder/positions" element={<ProtectedRoute><PositionsPage /></ProtectedRoute>} />
              <Route path="/builder/board" element={<ProtectedRoute><BoardPage /></ProtectedRoute>} />
            </>
          )}
          {/* סד"פ — procedure quiz (feature-flagged, default OFF — see PROCEDURES_ENABLED). */}
          {PROCEDURES_ENABLED && (
            <>
              <Route path="/procedures" element={<ProtectedRoute><ProceduresPage /></ProtectedRoute>} />
              <Route path="/procedures/:id" element={<ProtectedRoute><ProcedureDetailPage /></ProtectedRoute>} />
            </>
          )}
          <Route path="*" element={<Navigate to="/guards" replace />} />
        </Routes>
      </main>
    </>
  );
}
