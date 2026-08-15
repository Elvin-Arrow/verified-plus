import { NavLink, Outlet } from 'react-router-dom'
import SeedReplayControl from '../../components/SeedReplayControl.jsx'
import './DashboardLayout.css'

// FE-04: docs/ui-spec.md §4 — shared dashboard chrome (tab bar + Seed/Replay).
// Tab labels deliberately never show a raw item-count badge (§4's rationale:
// content urgency, not a bouncing tab number, is where priority signal lives).
const TABS = [
  { to: 'intake-inbox', label: 'Intake & Verification' },
  { to: 'dispatch-queue', label: 'Dispatch Queue' },
  { to: 'quarantine', label: 'Quarantine' },
  { to: 'archive', label: 'Archive' },
]

export default function DashboardLayout() {
  return (
    <div>
      <nav className="dashboard-tabbar" aria-label="Dashboard sections">
        <div className="dashboard-tabs">
          {TABS.map((tab) => (
            <NavLink key={tab.to} to={tab.to} className="dashboard-tab">
              {tab.label}
            </NavLink>
          ))}
        </div>
        <SeedReplayControl />
      </nav>
      <main className="dashboard-content">
        <Outlet />
      </main>
    </div>
  )
}
