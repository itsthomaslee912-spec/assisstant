export type Role = "admin" | "bidder";
export type UserStatus = "active" | "deactive";
export type JobStatus = "pending" | "applied" | "canceled";
export type WorkModel = "" | "on-site" | "hybrid" | "remote";
export type BotCheckStatus = "pending" | "pass" | "failure";

export interface ProfileSummary { id: number; first_name: string; last_name: string; email: string }
export interface User {
  id: number; email: string; user_id: string; status: UserStatus; role: Role;
  per_bid_pay_amount: number | null; crypto_address: string | null; profiles: ProfileSummary[]; created_at: string;
}
export interface Profile extends ProfileSummary {
  phone_number: string; linkedin: string; github: string; personal_website: string; portfolio: string;
  race: string; asian_region: string; salary: number | null; date_of_birth: string | null;
  street: string; city: string; state: string; zipcode: string; current_company: string;
  gender: string; visa_status: string; origin_ethnicity: string; veteran_status: string;
  disability_status: string; university: string; degree: string; major: string; duration: string;
  availability: string; resume_path: string | null; created_at: string; updated_at: string;
}
export interface Job {
  id: number; profile_id: number; company_name: string; role: string; job_link: string;
  work_model: WorkModel; status: JobStatus; bot_check_status: BotCheckStatus; application_date: string; created_at: string; submitted_at: string | null; updated_at: string;
}
export interface Page<T> { items: T[]; total: number; page: number; page_size: number }
export interface Point { label: string; value: number }
export interface BidderDashboard { profiles: ProfileSummary[]; applied_count: number; bot_check_pass_count: number; paid_amount: number; series: Point[] }
export interface PayCard { user_id: number; bidder_name: string; bot_check_pass_count: number; per_bid_pay_amount: number; paid_amount: number }
export interface AdminDashboard { total_profiles: number; active_bidders: number; applications_count: number; paid_amount_total: number; pay_cards: PayCard[]; profiles: ProfileSummary[]; profile_series: Record<string, Point[]> }
