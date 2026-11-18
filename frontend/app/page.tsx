import { redirect } from "next/navigation";

// This route only redirects, so skip Cache Components' instant-navigation check.
export const instant = false;

export default function Home() {
  redirect("/experiments");
}
