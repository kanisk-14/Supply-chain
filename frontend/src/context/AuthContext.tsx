"use client";

import React, { createContext, useContext, useState, useEffect, ReactNode } from "react";
import { User, UserRole, Permission } from "@/types/api";
import { authApi, getStoredToken, setStoredToken, removeStoredToken } from "@/lib/api";
import { useRouter } from "next/navigation";

const ROLE_PERMISSIONS: Record<UserRole, Permission[]> = {
  ADMIN: [
    "users:read",
    "users:write",
    "suppliers:read",
    "suppliers:write",
    "products:read",
    "products:write",
    "warehouses:read",
    "warehouses:write",
    "inventory:read",
    "inventory:write",
    "inventory:transactions:read",
    "orders:read",
    "orders:write",
    "shipments:read",
    "shipments:write",
    "analytics:read",
    "alerts:read",
  ],
  WAREHOUSE_MANAGER: [
    "users:read",
    "suppliers:read",
    "products:read",
    "warehouses:read",
    "warehouses:write",
    "inventory:read",
    "inventory:write",
    "inventory:transactions:read",
    "orders:read",
    "shipments:read",
    "shipments:write",
    "analytics:read",
    "alerts:read",
  ],
  SUPPLY_CHAIN_MANAGER: [
    "users:read",
    "suppliers:read",
    "suppliers:write",
    "products:read",
    "products:write",
    "warehouses:read",
    "warehouses:write",
    "inventory:read",
    "inventory:write",
    "inventory:transactions:read",
    "orders:read",
    "orders:write",
    "shipments:read",
    "shipments:write",
    "analytics:read",
    "alerts:read",
  ],
  ANALYST: [
    "users:read",
    "suppliers:read",
    "products:read",
    "warehouses:read",
    "inventory:read",
    "inventory:transactions:read",
    "orders:read",
    "shipments:read",
    "analytics:read",
    "alerts:read",
  ],
};

interface AuthContextType {
  user: User | null;
  token: string | null;
  isLoading: boolean;
  isAuthenticated: boolean;
  login: (token: string) => Promise<void>;
  logout: () => void;
  hasPermission: (...permissions: Permission[]) => boolean;
  hasRole: (...roles: UserRole[]) => boolean;
  refreshUser: () => Promise<void>;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [token, setToken] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const router = useRouter();

  const refreshUser = async () => {
    try {
      const currentUser = await authApi.me();
      setUser(currentUser);
    } catch (err) {
      removeStoredToken();
      setToken(null);
      setUser(null);
    }
  };

  useEffect(() => {
    const initAuth = async () => {
      const storedToken = getStoredToken();
      if (storedToken) {
        setToken(storedToken);
        try {
          const currentUser = await authApi.me();
          setUser(currentUser);
        } catch (err) {
          removeStoredToken();
          setToken(null);
          setUser(null);
        }
      }
      setIsLoading(false);
    };

    initAuth();
  }, []);

  const login = async (newToken: string) => {
    setStoredToken(newToken);
    setToken(newToken);
    try {
      const currentUser = await authApi.me();
      setUser(currentUser);
      router.push("/");
    } catch (err) {
      removeStoredToken();
      setToken(null);
      setUser(null);
      throw err;
    }
  };

  const logout = () => {
    removeStoredToken();
    setToken(null);
    setUser(null);
    router.push("/login");
  };

  const hasPermission = (...permissions: Permission[]): boolean => {
    if (!user) return false;
    const userPermissions = ROLE_PERMISSIONS[user.role] || [];
    return permissions.every((p) => userPermissions.includes(p));
  };

  const hasRole = (...roles: UserRole[]): boolean => {
    if (!user) return false;
    return roles.includes(user.role);
  };

  return (
    <AuthContext.Provider
      value={{
        user,
        token,
        isLoading,
        isAuthenticated: !!user,
        login,
        logout,
        hasPermission,
        hasRole,
        refreshUser,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error("useAuth must be used within an AuthProvider");
  }
  return context;
}

