import { useEffect, useState } from "react";
import { useAuthStore } from "@/store/authStore";
import { paymentsApi, loansApi, type Payment, type Loan } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";

const loanStateLabel: Record<string, string> = {
  initial: "در انتظار",
  active: "فعال",
  no_one: "بدون برنده",
};

const loanStateBadgeVariant: Record<
  string,
  "default" | "secondary" | "destructive" | "outline"
> = {
  initial: "secondary",
  active: "default",
  no_one: "destructive",
};

export function DashboardPage() {
  const { user, fetchMe } = useAuthStore();
  const [payments, setPayments] = useState<Payment[]>([]);
  const [loans, setLoans] = useState<Loan[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const load = async () => {
      await fetchMe();
      const [p, l] = await Promise.all([
        paymentsApi.myPayments(),
        loansApi.myHistory(),
      ]);
      setPayments(p);
      setLoans(l);
      setLoading(false);
    };
    load();
  }, [fetchMe]);

  if (loading) {
    return (
      <div className="text-center py-12 text-muted-foreground">
        در حال بارگذاری...
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <h1 className="text-3xl font-bold">داشبورد من</h1>

      {/* User Info */}
      {user && (
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm font-medium text-muted-foreground">
                موجودی
              </CardTitle>
            </CardHeader>
            <CardContent>
              <p className="text-2xl font-bold">
                {user.balance}{" "}
                <span className="text-sm text-muted-foreground">USDT</span>
              </p>
            </CardContent>
          </Card>
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm font-medium text-muted-foreground">
                مبلغ درخواست وام
              </CardTitle>
            </CardHeader>
            <CardContent>
              <p className="text-2xl font-bold">
                {user.loan_request_amount}{" "}
                <span className="text-sm text-muted-foreground">USDT</span>
              </p>
            </CardContent>
          </Card>
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm font-medium text-muted-foreground">
                وضعیت وام
              </CardTitle>
            </CardHeader>
            <CardContent>
              <Badge variant={user.has_active_loan ? "default" : "secondary"}>
                {user.has_active_loan ? "وام فعال دارد" : "بدون وام فعال"}
              </Badge>
            </CardContent>
          </Card>
        </div>
      )}

      {/* Payments */}
      <Card>
        <CardHeader>
          <CardTitle>تاریخچه پرداخت‌های من</CardTitle>
        </CardHeader>
        <CardContent>
          {payments.length === 0 ? (
            <p className="text-muted-foreground text-sm">
              هنوز پرداختی ثبت نشده است.
            </p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b">
                    <th className="text-right py-2 px-3 font-medium">
                      تاریخ (جلالی)
                    </th>
                    <th className="text-right py-2 px-3 font-medium">
                      مبلغ کل
                    </th>
                    <th className="text-right py-2 px-3 font-medium">
                      حق عضویت
                    </th>
                    <th className="text-right py-2 px-3 font-medium">
                      قسط وام
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {payments.map((p) => (
                    <tr
                      key={p.id}
                      className="border-b last:border-0 hover:bg-muted/50"
                    >
                      <td className="py-2 px-3">
                        {p.jalali_year}/
                        {String(p.jalali_month).padStart(2, "0")}
                      </td>
                      <td className="py-2 px-3 font-mono">{p.amount} USDT</td>
                      <td className="py-2 px-3 font-mono">
                        {p.membership_fee.amount} USDT
                      </td>
                      <td className="py-2 px-3 font-mono">
                        {p.loan_payment ? `${p.loan_payment.amount} USDT` : "—"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Loans */}
      <Card>
        <CardHeader>
          <CardTitle>تاریخچه وام‌های من</CardTitle>
        </CardHeader>
        <CardContent>
          {loans.length === 0 ? (
            <p className="text-muted-foreground text-sm">
              هنوز وامی دریافت نشده است.
            </p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b">
                    <th className="text-right py-2 px-3 font-medium">
                      تاریخ (جلالی)
                    </th>
                    <th className="text-right py-2 px-3 font-medium">وضعیت</th>
                    <th className="text-right py-2 px-3 font-medium">
                      مبلغ وام
                    </th>
                    <th className="text-right py-2 px-3 font-medium">
                      پرداخت شده
                    </th>
                    <th className="text-right py-2 px-3 font-medium">مانده</th>
                  </tr>
                </thead>
                <tbody>
                  {loans.map((l) => (
                    <tr
                      key={l.id}
                      className="border-b last:border-0 hover:bg-muted/50"
                    >
                      <td className="py-2 px-3">
                        {l.jalali_year}/
                        {String(l.jalali_month).padStart(2, "0")}
                      </td>
                      <td className="py-2 px-3">
                        <Badge
                          variant={loanStateBadgeVariant[l.state] ?? "outline"}
                        >
                          {loanStateLabel[l.state] ?? l.state}
                        </Badge>
                      </td>
                      <td className="py-2 px-3 font-mono">
                        {l.amount ? `${l.amount} USDT` : "—"}
                      </td>
                      <td className="py-2 px-3 font-mono">
                        {l.total_paid} USDT
                      </td>
                      <td className="py-2 px-3 font-mono">
                        {l.remaining_balance} USDT
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
