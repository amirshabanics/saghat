/// <reference types="vite/client" />

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "/api";

function getToken(): string | null {
  return localStorage.getItem("access_token");
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const token = getToken();
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(options.headers as Record<string, string>),
  };
  if (token) {
    headers["Authorization"] = `Bearer ${token}`;
  }

  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...options,
    headers,
  });

  if (!response.ok) {
    const error = await response
      .json()
      .catch(() => ({ detail: "Unknown error" }));
    throw {
      status: response.status,
      detail: error.detail ?? JSON.stringify(error),
    };
  }

  if (response.status === 204) return undefined as T;
  return response.json();
}

// ── Types ──────────────────────────────────────────────────────────────────────

export interface User {
  id: number;
  username: string;
  first_name: string;
  last_name: string;
  email: string;
  is_main: boolean;
  balance: string;
  loan_request_amount: string;
  has_active_loan: boolean;
}

export interface Config {
  min_membership_fee: string;
  max_month_for_loan_payment: number;
  min_amount_for_loan_payment: string;
}

export interface LoanPaymentInfo {
  loan_id: string;
  amount: string;
}

export interface MembershipFeeInfo {
  amount: string;
}

export interface Payment {
  id: string;
  user_id: number;
  amount: string;
  jalali_year: number;
  jalali_month: number;
  bitpin_payment_id: string;
  membership_fee: MembershipFeeInfo;
  loan_payment: LoanPaymentInfo | null;
}

export interface LoanPaymentRecord {
  id: string;
  amount: string;
  jalali_year: number;
  jalali_month: number;
}

export interface Loan {
  id: string;
  user_id: number | null;
  username: string | null;
  amount: string | null;
  state: "initial" | "active" | "no_one";
  jalali_year: number;
  jalali_month: number;
  min_amount_for_each_payment: string | null;
  total_paid: string;
  remaining_balance: string;
  log: {
    not_participated: Array<{
      user_id: number;
      username: string;
      reason: string;
    }>;
    participated: Array<{ user_id: number; username: string; point: string }>;
    selected: string | null;
    random_pool: string[];
  };
  payments: LoanPaymentRecord[];
}

export interface StartLoanResponse {
  loan: Loan;
  message: string;
}

export interface LoginResponse {
  access_token: string;
  token_type: string;
  user_id: number;
  username: string;
  is_main: boolean;
}

export interface PaymentRequest {
  membership_fee: string;
  loan: string | null;
  loan_request_amount: string | null;
  bitpin_payment_id: string;
}

// ── Auth ───────────────────────────────────────────────────────────────────────

export const authApi = {
  login: (username: string, password: string) =>
    request<LoginResponse>("/auth/login", {
      method: "POST",
      body: JSON.stringify({ username, password }),
    }),
  me: () => request<User>("/auth/me"),
  users: () => request<User[]>("/auth/users"),
};

// ── Payments ───────────────────────────────────────────────────────────────────

export const paymentsApi = {
  config: () => request<Config>("/payments/config"),
  myPayments: () => request<Payment[]>("/payments/my-payments"),
  pay: (data: PaymentRequest) =>
    request<Payment>("/payments/pay", {
      method: "POST",
      body: JSON.stringify(data),
    }),
};

// ── Loans ──────────────────────────────────────────────────────────────────────

export const loansApi = {
  myHistory: () => request<Loan[]>("/loans/my-history"),
  history: () => request<Loan[]>("/loans/history"),
  start: () => request<StartLoanResponse>("/loans/start", { method: "POST" }),
  get: (loanId: string) => request<Loan>(`/loans/${loanId}`),
};
