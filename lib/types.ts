export type Subject = "Mechanical Engineering" | "Computer Science" | "Civil Engineering";
export type StudyLevel = "Bachelor" | "Master";
export type ResearchStatus = "Pending" | "Researched" | "Researched – needs recheck";
export type FieldState = "Found" | "Not found" | "Conflict" | "Changed" | "Edited" | "Approved";

export interface University { index: number; qsRank: number; name: string; country: string; region: string; website: string; subjects: Subject[] }
export interface FieldValue { value: string; sourceUrl: string; lastVerified: string; state: FieldState; secondValue?: string; secondSourceUrl?: string; previousValue?: string }
export interface Programme { universityId: string; subject: Subject; studyLevel: StudyLevel; degreeProgram: string; notes: string; researchStatus: ResearchStatus; deadline: FieldValue; tuitionInternational: FieldValue; entryRequirements: FieldValue; scholarships: FieldValue; studySubjects: FieldValue }
export type RunStatus = "Completed" | "Running" | "Failed" | "Cancelled" | "Queued";
export interface Run { id: string; type: "Manual" | "Scheduled"; scope: string; started: string; status: RunStatus; failed: number; progress: number }
export interface Schedule { id: string; name: string; scope: string; subjects: Subject[]; frequency: string; nextRun: string; lastRun: string; lastStatus: RunStatus; enabled: boolean }
export interface ExportRecord { id: string; filename: string; scope: string; layout: string; format: "CSV" | "XLSX"; rows: number; createdAt: string }
