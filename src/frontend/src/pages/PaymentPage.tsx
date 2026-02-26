import { useEffect, useState } from "react";
import { useAuthStore } from "@/store/authStore";
import { useConfigStore } from "@/store/configStore";
import { paymentsApi, loansApi, type Loan } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  CardDescription,
} from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";

export function PaymentPage() {
  const { user, fetchMe } = useAuthStore();
  const { config, fetchConfig } = useConfigStore();

  // Payment form state
  const [membershipFee, setMembershipFee] = useState("");
  const [loanAmount, setLoanAmount] = useState("");
  const [loanRequestAmount, setLoanRequestAmount] = useState("");
  const [bitpinId, setBitpinId] = useState("");
  const [payError, setPayError] = useState<string | null>(null);
  const [paySuccess, setPaySuccess] = useState(false);
  const [payLoading, setPayLoading] = useState(false);

  // Loan assignment state
  const [currentLoan, setCurrentLoan] = useState<Loan | null | undefined>(
    undefined,
  ); // undefined = not loaded
  const [loanLoading, setLoanLoading] = useState(false);
  const [loanError, setLoanError] = useState<string | null>(null);
  const [startMessage, setStartMessage] = useState<string | null>(null);

  useEffect(() => {
    fetchMe();
    fetchConfig();
    loadCurrentLoan();
    // fetchMe and fetchConfig are stable Zustand actions; loadCurrentLoan is defined in this scope
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const loadCurrentLoan = async () => {
    try {
      const loans = await loansApi.myHistory();
      // Show the most recent loan (first in list) as the current month candidate
      setCurrentLoan(loans.length > 0 ? loans[0] : null);
    } catch {
      setCurrentLoan(null);
    }
  };

  const handlePay = async (e: React.FormEvent) => {
    e.preventDefault();
    setPayError(null);
    setPaySuccess(false);
    setPayLoading(true);
    try {
      await paymentsApi.pay({
        membership_fee: membershipFee,
        loan: user?.has_active_loan ? loanAmount : null,
        loan_request_amount: loanRequestAmount || null,
        bitpin_payment_id: bitpinId,
      });
      setPaySuccess(true);
      setMembershipFee("");
      setLoanAmount("");
      setLoanRequestAmount("");
      setBitpinId("");
      await fetchMe();
    } catch (err: unknown) {
      const apiErr = err as { detail?: string };
      setPayError(apiErr.detail ?? "خطا در ثبت پرداخت.");
    } finally {
      setPayLoading(false);
    }
  };

  const handleStartLoan = async () => {
    setLoanError(null);
    setLoanLoading(true);
    try {
      const result = await loansApi.start();
      setCurrentLoan(result.loan);
      setStartMessage(result.message);
    } catch (err: unknown) {
      const apiErr = err as { detail?: string };
      setLoanError(apiErr.detail ?? "خطا در شروع قرعه‌کشی.");
    } finally {
      setLoanLoading(false);
    }
  };

  return (
    <div className="space-y-6 max-w-2xl mx-auto">
      <h1 className="text-3xl font-bold">پرداخت</h1>

      {/* Payment Form */}
      <Card>
        <CardHeader>
          <CardTitle>ثبت پرداخت ماهانه</CardTitle>
          <CardDescription>
            {config && `حداقل حق عضویت: ${config.min_membership_fee} USDT`}
          </CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={handlePay} className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="membership_fee">حق عضویت (USDT)</Label>
              <Input
                id="membership_fee"
                type="number"
                step="0.00000001"
                min={config?.min_membership_fee ?? "0"}
                value={membershipFee}
                onChange={(e) => setMembershipFee(e.target.value)}
                required
                dir="ltr"
                placeholder={config?.min_membership_fee ?? "20"}
              />
            </div>

            {user?.has_active_loan && (
              <div className="space-y-2">
                <Label htmlFor="loan_amount">قسط وام (USDT)</Label>
                <Input
                  id="loan_amount"
                  type="number"
                  step="0.00000001"
                  min={config?.min_amount_for_loan_payment ?? "0"}
                  value={loanAmount}
                  onChange={(e) => setLoanAmount(e.target.value)}
                  required
                  dir="ltr"
                  placeholder={config?.min_amount_for_loan_payment ?? "20"}
                />
              </div>
            )}

            <div className="space-y-2">
              <Label htmlFor="loan_request">
                مبلغ درخواست وام (اختیاری، USDT)
              </Label>
              <Input
                id="loan_request"
                type="number"
                step="0.00000001"
                min="0"
                value={loanRequestAmount}
                onChange={(e) => setLoanRequestAmount(e.target.value)}
                dir="ltr"
                placeholder="0 برای انصراف از وام"
              />
            </div>

            <div className="space-y-2">
              <Label htmlFor="bitpin_id">شناسه تراکنش بیت‌پین</Label>
              <Input
                id="bitpin_id"
                type="text"
                value={bitpinId}
                onChange={(e) => setBitpinId(e.target.value)}
                required
                dir="ltr"
                placeholder="transaction ID from Bitpin"
              />
            </div>

            {payError && <p className="text-sm text-destructive">{payError}</p>}
            {paySuccess && (
              <p className="text-sm text-green-600">پرداخت با موفقیت ثبت شد.</p>
            )}

            <Button type="submit" className="w-full" disabled={payLoading}>
              {payLoading ? "در حال ثبت..." : "ثبت پرداخت"}
            </Button>
          </form>
        </CardContent>
      </Card>

      <Separator />

      {/* Loan Assignment */}
      <Card>
        <CardHeader>
          <CardTitle>قرعه‌کشی وام ماه جاری</CardTitle>
          <CardDescription>
            شروع قرعه‌کشی برای تعیین برنده وام این ماه
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          {currentLoan === undefined ? (
            <p className="text-muted-foreground text-sm">در حال بارگذاری...</p>
          ) : currentLoan === null ? (
            <div className="space-y-3">
              <p className="text-sm text-muted-foreground">
                هنوز قرعه‌کشی برای این ماه انجام نشده است.
              </p>
              {loanError && (
                <p className="text-sm text-destructive">{loanError}</p>
              )}
              <Button
                onClick={handleStartLoan}
                disabled={loanLoading}
                variant="outline"
              >
                {loanLoading ? "در حال قرعه‌کشی..." : "شروع قرعه‌کشی"}
              </Button>
            </div>
          ) : (
            <LoanResult loan={currentLoan} message={startMessage} />
          )}
        </CardContent>
      </Card>
    </div>
  );
}

function LoanResult({ loan, message }: { loan: Loan; message: string | null }) {
  const loanStateLabel: Record<string, string> = {
    initial: "در انتظار",
    active: "فعال — برنده مشخص شد",
    no_one: "بدون برنده",
  };

  return (
    <div className="space-y-4">
      {message && (
        <p className="text-sm font-medium text-green-600">{message}</p>
      )}

      <div className="flex items-center gap-3">
        <span className="text-sm font-medium">نتیجه:</span>
        <Badge
          variant={
            loan.state === "active"
              ? "default"
              : loan.state === "no_one"
                ? "destructive"
                : "secondary"
          }
        >
          {loanStateLabel[loan.state] ?? loan.state}
        </Badge>
      </div>

      {loan.state === "active" && loan.username && (
        <div className="rounded-lg bg-muted p-4 space-y-2">
          <p className="font-semibold">
            🎉 برنده: <span className="text-primary">{loan.username}</span>
          </p>
          <p className="text-sm text-muted-foreground">
            مبلغ وام: <span className="font-mono">{loan.amount} USDT</span>
          </p>
        </div>
      )}

      {loan.log.participated.length > 0 && (
        <div className="space-y-2">
          <p className="text-sm font-medium">
            شرکت‌کنندگان ({loan.log.participated.length} نفر):
          </p>
          <div className="flex flex-wrap gap-2">
            {loan.log.participated.map((p) => (
              <Badge key={p.user_id} variant="outline" className="text-xs">
                {p.username} — امتیاز: {p.point}
              </Badge>
            ))}
          </div>
        </div>
      )}

      {loan.log.not_participated.length > 0 && (
        <div className="space-y-2">
          <p className="text-sm font-medium text-muted-foreground">
            عدم شرکت ({loan.log.not_participated.length} نفر):
          </p>
          <div className="flex flex-wrap gap-2">
            {loan.log.not_participated.map((p) => (
              <Badge key={p.user_id} variant="secondary" className="text-xs">
                {p.username}: {p.reason}
              </Badge>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
