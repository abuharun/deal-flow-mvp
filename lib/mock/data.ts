import type { ExportRecord, FieldValue, Programme, Run, Schedule, Subject, University } from "@/lib/types";

const subjects: Subject[] = ["Mechanical Engineering", "Computer Science", "Civil Engineering"];
const raw = [
  ["mit",1,"Massachusetts Institute of Technology","United States","North America","https://web.mit.edu",subjects],
  ["imperial",2,"Imperial College London","United Kingdom","Europe","https://imperial.ac.uk",[subjects[0],subjects[2]]],
  ["eth-zurich",3,"ETH Zurich","Switzerland","Europe","https://ethz.ch",subjects],
  ["nus",4,"National University of Singapore","Singapore","Asia","https://nus.edu.sg",[subjects[0],subjects[1]]],
  ["cambridge",5,"University of Cambridge","United Kingdom","Europe","https://cam.ac.uk",subjects],
  ["delft",6,"Delft University of Technology","Netherlands","Europe","https://tudelft.nl",[subjects[0],subjects[2]]],
  ["tsinghua",8,"Tsinghua University","China (Mainland)","Asia","https://tsinghua.edu.cn",subjects],
  ["kth",12,"KTH Royal Institute of Technology","Sweden","Europe","https://kth.se",[subjects[0],subjects[1]]],
  ["polimi",14,"Politecnico di Milano","Italy","Europe","https://polimi.it",[subjects[0],subjects[2]]],
  ["uq",41,"The University of Queensland","Australia","Oceania","https://uq.edu.au",subjects],
  ["tum",19,"Technical University of Munich","Germany","Europe","https://tum.de",subjects],
  ["kaist",24,"KAIST","South Korea","Asia","https://kaist.ac.kr",[subjects[0],subjects[1]]],
  ["toronto",21,"University of Toronto","Canada","North America","https://utoronto.ca",subjects],
  ["tokyo",32,"The University of Tokyo","Japan","Asia","https://u-tokyo.ac.jp",subjects],
  ["epfl",16,"EPFL","Switzerland","Europe","https://epfl.ch",subjects],
] as const;
export const universities: University[] = raw.map((r,index)=>({index:index+1,qsRank:r[1],name:r[2],country:r[3],region:r[4],website:r[5],subjects:[...r[6]]}));
export const universityIds = raw.map(r=>r[0]);
const fv=(value:string,state:FieldValue["state"]="Found", sourceUrl="https://example.edu/programme", extra:Partial<FieldValue>={}):FieldValue=>({value,sourceUrl,lastVerified:"08 Oct 2026",state,...extra});
export const programmes: Programme[] = raw.flatMap((r,ui)=> r[6].flatMap((subject,si)=> (["Bachelor","Master"] as const).map((studyLevel,li)=>({
  universityId:r[0], subject, studyLevel, degreeProgram: ui===0 ? (["SB in Mechanical Engineering (Course 2)","SM in Mechanical Engineering","SB in Computer Science and Engineering (6-3)","MEng in Electrical Engineering and Computer Science","SB in Civil and Environmental Engineering (Course 1)","SM in Civil and Environmental Engineering"][si*2+li]) : `${studyLevel} of ${subject}`,
  notes: r[0]==="cambridge" ? "Closest-equivalent programme; General Engineering is listed under Mechanical Engineering." : r[0]==="tsinghua" ? "University site failed with HTTP 403." : "",
  researchStatus: r[0]==="delft"||r[0]==="polimi" ? "Pending" : r[0]==="eth-zurich"||r[0]==="tsinghua" ? "Researched – needs recheck" : "Researched",
  deadline: r[0]==="eth-zurich" ? fv("30 Nov 2026","Conflict","https://ethz.ch/source-a",{secondValue:"15 Dec 2026",secondSourceUrl:"https://ethz.ch/source-b"}) : fv("Semester 1, 2027: applications close 30 Nov 2026", li ? "Found":"Approved"),
  tuitionInternational: r[0]==="kth" ? fv("SEK 335,000 total (2 years)","Changed","https://kth.se/fees",{previousValue:"SEK 310,000 total (2 years)"}) : fv(r[0]==="uq"?"AUD 58,384 per year (2027, indicative)":"USD 62,396 / year"),
  entryRequirements: fv("Bachelor equivalent; mathematics and physics; IELTS 6.5",ui===9&&li===0?"Edited":"Found"),
  scholarships: li ? fv("Not found — searched 41 pages","Not found") : fv("International excellence scholarship: 25% tuition reduction","Found"),
  studySubjects: fv("Engineering Design, Thermodynamics, Fluid Mechanics, Dynamics, Mechanical Design"),
}))));
export const runs:Run[]=[
  {id:"R-0143",type:"Manual",scope:"42 unis · ME, CS · Bachelor + Master",started:"Today 14:02",status:"Running",failed:1,progress:42},
  {id:"R-0142",type:"Scheduled",scope:"Top 150 · ME, CS, CE",started:"08 Oct 2026",status:"Completed",failed:6,progress:100},
  {id:"R-0141",type:"Manual",scope:"12 unis · CE · Master",started:"02 Oct 2026",status:"Completed",failed:0,progress:100},
  {id:"R-0140",type:"Scheduled",scope:"Stale rows sweep",started:"28 Sep 2026",status:"Cancelled",failed:0,progress:21},
];
export const schedules:Schedule[]=[
 {id:"annual",name:"Annual fees & deadlines",scope:"Top 150, all subjects",subjects,frequency:"Yearly on 01 Nov",nextRun:"01 Nov 2026",lastRun:"01 Nov 2025",lastStatus:"Completed",enabled:true},
 {id:"entry",name:"Entry requirements & study subjects",scope:"All universities",subjects:subjects.slice(0,2),frequency:"Every 18 months",nextRun:"15 Jan 2027",lastRun:"15 Jul 2025",lastStatus:"Completed",enabled:true},
 {id:"stale",name:"Stale rows sweep",scope:"Freshness: stale",subjects,frequency:"Every 3 months",nextRun:"01 Dec 2026",lastRun:"28 Sep 2026",lastStatus:"Cancelled",enabled:true},
 {id:"scholarships",name:"Scholarships check",scope:"Top 50, Computer Science",subjects:[subjects[1]],frequency:"Custom: 1 Mar, 1 Sep",nextRun:"Paused",lastRun:"01 Mar 2026",lastStatus:"Completed",enabled:false},
];
export const exportsData:ExportRecord[]=[
 {id:"e1",filename:"bvosita_mechanical-engineering_2026-10-08.xlsx",scope:"Run R-0142",layout:"One file per subject",format:"XLSX",rows:1186,createdAt:"08 Oct 2026 17:40"},
 {id:"e2",filename:"bvosita_computer-science_2026-10-08.xlsx",scope:"Run R-0142",layout:"One file per subject",format:"XLSX",rows:1302,createdAt:"08 Oct 2026 17:40"},
 {id:"e3",filename:"bvosita_all-subjects_2026-09-30.csv",scope:"Everything",layout:"Combined + Subject column",format:"CSV",rows:3301,createdAt:"30 Sep 2026 09:12"},
];
