"use client";

import React, { ReactNode, useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useAuth } from "@/context/AuthContext";
import {
  LayoutDashboard,
  Boxes,
  ShoppingCart,
  Truck,
  Package,
  Building2,
  Warehouse,
  AlertTriangle,
  LogOut,
  Menu,
  X,
  User as UserIcon,
} from "lucide-react";

interface AppLayoutProps {
  children: ReactNode;
}

export default function AppLayout({ children }: AppLayoutProps) {
  const pathname = usePathname();
  const { user, logout } = useAuth();
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);

  const navigation = [
    { name: "Dashboard", href: "/", icon: LayoutDashboard },
    { name: "Inventory", href: "/inventory", icon: Boxes },
    { name: "Orders", href: "/orders", icon: ShoppingCart },
    { name: "Shipments", href: "/shipments", icon: Truck },
    { name: "Products", href: "/products", icon: Package },
    { name: "Suppliers", href: "/suppliers", icon: Building2 },
    { name: "Warehouses", href: "/warehouses", icon: Warehouse },
    { name: "Alerts", href: "/alerts", icon: AlertTriangle },
  ];

  const roleColors: Record<string, string> = {
    ADMIN: "bg-purple-100 text-purple-800 border-purple-200",
    SUPPLY_CHAIN_MANAGER: "bg-blue-100 text-blue-800 border-blue-200",
    WAREHOUSE_MANAGER: "bg-amber-100 text-amber-800 border-amber-200",
    ANALYST: "bg-slate-100 text-slate-800 border-slate-200",
  };

  return (
    <div className="min-h-screen bg-slate-50 text-slate-900 flex">
      {/* Desktop Sidebar */}
      <aside className="hidden md:flex md:w-64 md:flex-col fixed inset-y-0 z-30 border-r border-slate-200 bg-white">
        <div className="flex h-16 items-center px-6 border-b border-slate-100">
          <Link href="/" className="flex items-center gap-2">
            <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-indigo-600 text-white font-bold">
              SC
            </div>
            <span className="font-semibold text-slate-800 text-base tracking-tight">
              Supply Chain
            </span>
          </Link>
        </div>

        <div className="flex flex-1 flex-col justify-between overflow-y-auto px-3 py-4">
          <nav className="space-y-1">
            {navigation.map((item) => {
              const isActive =
                item.href === "/"
                  ? pathname === "/"
                  : pathname === item.href || pathname.startsWith(`${item.href}/`);
              const Icon = item.icon;
              return (
                <Link
                  key={item.name}
                  href={item.href}
                  className={`flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors ${
                    isActive
                      ? "bg-indigo-50 text-indigo-700 font-semibold"
                      : "text-slate-600 hover:bg-slate-50 hover:text-slate-900"
                  }`}
                >
                  <Icon
                    className={`h-4 w-4 ${
                      isActive ? "text-indigo-600" : "text-slate-400"
                    }`}
                  />
                  {item.name}
                </Link>
              );
            })}
          </nav>

          {/* User Profile in Sidebar Footer */}
          {user && (
            <div className="mt-auto border-t border-slate-100 pt-4 px-2">
              <div className="flex items-center gap-3 mb-3">
                <div className="flex h-9 w-9 items-center justify-center rounded-full bg-slate-100 text-slate-600">
                  <UserIcon className="h-5 w-5" />
                </div>
                <div className="min-w-0 flex-1">
                  <p className="truncate text-xs font-semibold text-slate-800">
                    {user.name}
                  </p>
                  <p className="truncate text-xs text-slate-500">{user.email}</p>
                </div>
              </div>
              <div className="mb-3">
                <span
                  className={`inline-block text-[10px] font-semibold px-2 py-0.5 rounded border uppercase tracking-wider ${
                    roleColors[user.role] || "bg-slate-100 text-slate-700"
                  }`}
                >
                  {user.role.replace(/_/g, " ")}
                </span>
              </div>
              <button
                onClick={logout}
                className="flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-xs font-medium text-slate-600 hover:bg-red-50 hover:text-red-700 transition-colors"
              >
                <LogOut className="h-3.5 w-3.5" />
                Sign out
              </button>
            </div>
          )}
        </div>
      </aside>

      {/* Mobile Header */}
      <div className="md:hidden fixed top-0 inset-x-0 z-40 flex h-14 items-center justify-between border-b border-slate-200 bg-white px-4">
        <Link href="/" className="flex items-center gap-2">
          <div className="flex h-7 w-7 items-center justify-center rounded bg-indigo-600 text-white font-bold text-xs">
            SC
          </div>
          <span className="font-semibold text-slate-800 text-sm">Supply Chain</span>
        </Link>
        <button
          onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
          className="rounded p-1 text-slate-600 hover:bg-slate-100"
        >
          {mobileMenuOpen ? <X className="h-6 w-6" /> : <Menu className="h-6 w-6" />}
        </button>
      </div>

      {/* Mobile Drawer */}
      {mobileMenuOpen && (
        <div className="md:hidden fixed inset-0 z-30 flex flex-col bg-white pt-14">
          <nav className="flex-1 space-y-1 p-4 overflow-y-auto">
            {navigation.map((item) => {
              const isActive =
                item.href === "/"
                  ? pathname === "/"
                  : pathname === item.href || pathname.startsWith(`${item.href}/`);
              const Icon = item.icon;
              return (
                <Link
                  key={item.name}
                  href={item.href}
                  onClick={() => setMobileMenuOpen(false)}
                  className={`flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium ${
                    isActive
                      ? "bg-indigo-50 text-indigo-700 font-semibold"
                      : "text-slate-600 hover:bg-slate-50"
                  }`}
                >
                  <Icon className={`h-5 w-5 ${isActive ? "text-indigo-600" : "text-slate-400"}`} />
                  {item.name}
                </Link>
              );
            })}
          </nav>
          {user && (
            <div className="border-t border-slate-100 p-4">
              <div className="flex items-center justify-between mb-2">
                <div>
                  <p className="text-sm font-medium text-slate-800">{user.name}</p>
                  <p className="text-xs text-slate-500">{user.email}</p>
                </div>
                <span
                  className={`text-[10px] font-semibold px-2 py-0.5 rounded border uppercase ${
                    roleColors[user.role] || "bg-slate-100"
                  }`}
                >
                  {user.role}
                </span>
              </div>
              <button
                onClick={() => {
                  setMobileMenuOpen(false);
                  logout();
                }}
                className="mt-2 flex w-full items-center justify-center gap-2 rounded-md bg-slate-100 py-2 text-xs font-medium text-red-600"
              >
                <LogOut className="h-4 w-4" /> Sign out
              </button>
            </div>
          )}
        </div>
      )}

      {/* Main Content Area */}
      <main className="flex-1 md:pl-64 flex flex-col min-h-screen pt-14 md:pt-0">
        <div className="p-4 sm:p-6 md:p-8 max-w-7xl w-full mx-auto">{children}</div>
      </main>
    </div>
  );
}

