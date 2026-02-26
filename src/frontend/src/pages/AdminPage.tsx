import { useEffect, useState } from "react";
import { authApi, loansApi, type User, type Loan } from "@/lib/api";
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

export function AdminPage() {
  const [users, setUsers] = useState<User[]>([]);
  const [loans, setLoans] = useState<Loan[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const load = async () => {
      const [u, l] = await Promise.all([authApi.users(), loansApi.history()]);
      setUsers(u);
      setLoans(l);
      setLoading(false);
    };
    load();
  }, []);

  if (loading) {
    return (
      <div className="text-center py-12 text-muted-foreground">
        در حال بارگذاری...
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <h1 className="text-3xl font-bold">پنل مدیریت</h1>

      {/* Users Table */}
      <Card>
        <CardHeader>
          <CardTitle>اعضای صندوق ({users.length} نفر)</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b">
                  <th className="text-right py-2 px-3 font-medium">
                    نام کاربری
                  </th>
                  <th className="text-right py-2 px-3 font-medium">نام</th>
                  <th className="text-right py-2 px-3 font-medium">موجودی</th>
                  <th className="text-right py-2 px-3 font-medium">
                    درخواست وام
                  </th>
                  <th className="text-right py-2 px-3 font-medium">وضعیت</th>
                  <th className="text-right py-2 px-3 font-medium">نقش</th>
                </tr>
              </thead>
              <tbody>
                {users.map((u) => (
                  <tr
                    key={u.id}
                    className="border-b last:border-0 hover:bg-muted/50"
                  >
                    <td className="py-2 px-3 font-mono">{u.username}</td>
                    <td className="py-2 px-3">
                      {[u.first_name, u.last_name].filter(Boolean).join(" ") ||
                        "—"}
                    </td>
                    <td className="py-2 px-3 font-mono">{u.balance} USDT</td>
                    <td className="py-2 px-3 font-mono">
                      {u.loan_request_amount} USDT
                    </td>
                    <td className="py-2 px-3">
                      <Badge
                        variant={u.has_active_loan ? "default" : "secondary"}
                      >
                        {u.has_active_loan ? "وام فعال" : "بدون وام"}
                      </Badge>
                    </td>
                    <td className="py-2 px-3">
                      {u.is_main ? (
                        <Badge>مدیر</Badge>
                      ) : (
                        <Badge variant="outline">عضو</Badge>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </CardContent>
      </Card>

      {/* Loans History */}
      <Card>
        <CardHeader>
          <CardTitle>تاریخچه کامل وام‌ها</CardTitle>
        </CardHeader>
        <CardContent>
          {loans.length === 0 ? (
            <p className="text-muted-foreground text-sm">
              هنوز وامی ثبت نشده است.
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
                    <th className="text-right py-2 px-3 font-medium">برنده</th>
                    <th className="text-right py-2 px-3 font-medium">مبلغ</th>
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
                      <td className="py-2 px-3">{l.username ?? "—"}</td>
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
