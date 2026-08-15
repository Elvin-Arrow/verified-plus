import { Outlet } from 'react-router-dom'

// FE-01 scaffold — full chrome (tab bar, Seed/Replay control) lands in FE-04/FE-14.
export default function DashboardLayout() {
  return (
    <div>
      <Outlet />
    </div>
  )
}
