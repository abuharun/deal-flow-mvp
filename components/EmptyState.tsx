import Link from "next/link";
export function EmptyState({title,description,action,href}:{title:string;description:string;action:string;href:string}){return <div className="statebox"><span className="stateicon"/><h2>{title}</h2><p>{description}</p><Link className="btn primary" href={href}>{action}</Link></div>}
