import { Suspense } from "react";
import { ExperimentHeaderSkeleton, ExperimentView } from "@/components/experiments/experiment-view";

export default function ExperimentPage({ params }: { params: Promise<{ id: string }> }) {
  return (
    <Suspense fallback={<ExperimentHeaderSkeleton />}>
      {params.then(({ id }) => (
        <ExperimentView id={id} />
      ))}
    </Suspense>
  );
}
