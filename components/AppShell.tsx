import {Sidebar} from "./Sidebar";
export function AppShell({children}:{children:React.ReactNode}){return <div className="appshell"><a className="skip" href="#main">Skip to content</a><Sidebar/><main id="main" className="main">{children}</main></div>}
