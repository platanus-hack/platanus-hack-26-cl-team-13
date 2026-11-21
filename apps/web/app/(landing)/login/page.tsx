import type { Metadata } from "next";
import { Suspense } from "react";
import { LoginForm } from "./login-form";

export const metadata: Metadata = { title: "Entrar · AIgis" };

export default function LoginPage() {
  return (
    <div className="flex justify-center py-10 sm:py-20">
      <Suspense>
        <LoginForm />
      </Suspense>
    </div>
  );
}
