import { useEffect } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useAuthStore } from "@/store/authStore";
import { useConfigStore } from "@/store/configStore";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import { LogOut, User } from "lucide-react";

export function Header() {
  const { user, logout } = useAuthStore();
  const { config, fetchConfig } = useConfigStore();
  const navigate = useNavigate();

  useEffect(() => {
    fetchConfig();
  }, [fetchConfig]);

  const handleLogout = () => {
    logout();
    navigate("/login");
  };

  return (
    <header className="border-b bg-card">
      <div className="container mx-auto px-4 py-3 flex items-center justify-between">
        <div className="flex items-center gap-4">
          <Link to="/dashboard" className="text-xl font-bold text-primary">
            صندوق صغات
          </Link>
          <Separator orientation="vertical" className="h-6" />
          <nav className="flex items-center gap-2">
            <Button variant="ghost" size="sm" asChild>
              <Link to="/dashboard">داشبورد</Link>
            </Button>
            <Button variant="ghost" size="sm" asChild>
              <Link to="/pay">پرداخت</Link>
            </Button>
            {user?.is_main && (
              <Button variant="ghost" size="sm" asChild>
                <Link to="/admin">مدیریت</Link>
              </Button>
            )}
          </nav>
        </div>

        <div className="flex items-center gap-3">
          {config && (
            <div className="hidden md:flex items-center gap-2 text-xs text-muted-foreground">
              <Badge variant="outline">
                حداقل حق عضویت: {config.min_membership_fee} USDT
              </Badge>
              <Badge variant="outline">
                حداکثر اقساط: {config.max_month_for_loan_payment} ماه
              </Badge>
              <Badge variant="outline">
                حداقل قسط: {config.min_amount_for_loan_payment} USDT
              </Badge>
            </div>
          )}
          <Separator orientation="vertical" className="h-6 hidden md:block" />
          <div className="flex items-center gap-2">
            <User className="h-4 w-4 text-muted-foreground" />
            <span className="text-sm font-medium">{user?.username}</span>
          </div>
          <Button
            variant="ghost"
            size="icon"
            onClick={handleLogout}
            title="خروج"
          >
            <LogOut className="h-4 w-4" />
          </Button>
        </div>
      </div>
    </header>
  );
}
