import { Suspense } from "react";
import { NewRunForm, NewRunSkeleton } from "@/components/cebra/NewRunForm";

export default function NewRunPage({ params }: { params: Promise<{ id: string }> }) {
  return (
    <Suspense fallback={<NewRunSkeleton />}>
      {params.then(({ id }) => (
        <NewRunForm id={id} />
      ))}
    </Suspense>
  );
}
