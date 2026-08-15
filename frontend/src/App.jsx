import { Navigate, Route, Routes } from 'react-router-dom'
import IntakeForm from './pages/intake/IntakeForm.jsx'
import DashboardLayout from './pages/dashboard/DashboardLayout.jsx'
import IntakeInboxView from './pages/dashboard/IntakeInboxView.jsx'
import DispatchQueueView from './pages/dashboard/DispatchQueueView.jsx'
import QuarantineView from './pages/dashboard/QuarantineView.jsx'
import ArchiveView from './pages/dashboard/ArchiveView.jsx'

// FE-01: routing shell — two entry points per docs/ui-spec.md §2.
export default function App() {
  return (
    <Routes>
      <Route path="/" element={<Navigate to="/intake" replace />} />
      <Route path="/intake" element={<IntakeForm />} />
      <Route path="/dashboard" element={<DashboardLayout />}>
        <Route index element={<Navigate to="intake-inbox" replace />} />
        <Route path="intake-inbox" element={<IntakeInboxView />} />
        <Route path="dispatch-queue" element={<DispatchQueueView />} />
        <Route path="quarantine" element={<QuarantineView />} />
        <Route path="archive" element={<ArchiveView />} />
      </Route>
      <Route path="*" element={<Navigate to="/intake" replace />} />
    </Routes>
  )
}
