"use client";
export function FilterBar({search,onSearch,children}:{search?:string;onSearch?:(v:string)=>void;children?:React.ReactNode}){return <div className="filterbar">{onSearch&&<label className="search"><span className="sr-only">Search</span><input value={search} onChange={e=>onSearch(e.target.value)} placeholder="Search university, country or website…"/></label>}{children}</div>}
