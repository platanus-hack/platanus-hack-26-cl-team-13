import { redirect } from "next/navigation";

// La galería de grabaciones vive en /demo/ataca
export default function ReplayIndex() {
  redirect("/demo/ataca");
}
