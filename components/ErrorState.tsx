import {ActionButton} from "./Toast";
export function ErrorState({title,description,action="Retry"}:{title:string;description:string;action?:string}){return <div className="statebox error"><h2>{title}</h2><p>{description}</p><ActionButton className="btn secondary">{action}</ActionButton></div>}
