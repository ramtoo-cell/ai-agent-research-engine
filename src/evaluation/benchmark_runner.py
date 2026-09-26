import asyncio
import logging
import math
import statistics
import time
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Tuple

from pydantic import BaseModel, Field, field_validator


class DatasetItem(BaseModel):
    """An individual item from a benchmark dataset."""
    item_id: str
    input_payload: Any
    expected_output: Any
    metadata: Dict[str, Any] = Field(default_factory=dict)


class BenchmarkDefinition(BaseModel):
    """Defines the configuration and inputs for a benchmark run."""
    benchmark_id: str
    name: str
    description: str = ""
    dataset: List[DatasetItem] = Field(..., description="The dataset to benchmark against")
    evaluator_names: List[str] = Field(..., description="List of evaluators to run on the outputs")
    parallelism: int = Field(default=5, ge=1, le=100, description="Number of concurrent execution slots")
    timeout_per_item_ms: int = Field(default=10000, description="Timeout for a single dataset item evaluation")
    metadata: Dict[str, Any] = Field(default_factory=dict)


class ExecutionMetrics(BaseModel):
    """Metrics related to the execution of a single benchmark item."""
    duration_ms: float = Field(..., description="Execution time in milliseconds")
    peak_memory_mb: Optional[float] = Field(default=None, description="Peak memory used, if tracked")
    token_count: Optional[int] = Field(default=None, description="Tokens generated, if applicable")
    success: bool = Field(default=True, description="Whether the inference succeeded")
    error_msg: Optional[str] = Field(default=None)


class ItemResult(BaseModel):
    """The result of evaluating a single dataset item."""
    item_id: str
    metrics: ExecutionMetrics
    evaluator_scores: Dict[str, float] = Field(..., description="Scores indexed by evaluator name")


class StatisticalSummary(BaseModel):
    """Statistical breakdown of a specific metric across the benchmark."""
    mean: float
    median: float
    std_dev: float
    min_val: float
    max_val: float
    p90: float
    p95: float
    p99: float
    confidence_interval_95: Tuple[float, float] = Field(description="95% CI bounds for the mean")


class BenchmarkResult(BaseModel):
    """The aggregated results of a full benchmark run."""
    run_id: str
    benchmark_id: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    total_items: int
    successful_items: int
    failed_items: int
    item_results: List[ItemResult] = Field(exclude=True)  # Exclude from simple JSON serialization
    timing_stats: StatisticalSummary
    accuracy_stats: Dict[str, StatisticalSummary] = Field(..., description="Stats per evaluator")
    metadata: Dict[str, Any] = Field(default_factory=dict)


class StatisticalAnalyzer:
    """Computes statistical summaries for benchmark metrics."""
    
    @staticmethod
    def _compute_ci(data: List[float], mean: float, std_dev: float) -> Tuple[float, float]:
        """Approximates 95% Confidence Interval for the mean using normal distribution."""
        n = len(data)
        if n < 2 or std_dev == 0.0:
            return (mean, mean)
        # Z-score for 95% CI is approx 1.96
        margin = 1.96 * (std_dev / math.sqrt(n))
        return (mean - margin, mean + margin)
        
    @classmethod
    def analyze(cls, data: List[float]) -> StatisticalSummary:
        """Analyzes a list of numerical data points."""
        if not data:
            return StatisticalSummary(
                mean=0.0, median=0.0, std_dev=0.0, min_val=0.0, max_val=0.0,
                p90=0.0, p95=0.0, p99=0.0, confidence_interval_95=(0.0, 0.0)
            )
            
        n = len(data)
        sorted_data = sorted(data)
        
        mean = statistics.mean(data)
        median = statistics.median(data)
        std_dev = statistics.stdev(data) if n > 1 else 0.0
        
        p90 = sorted_data[int(0.90 * n)] if n > 0 else 0.0
        p95 = sorted_data[int(0.95 * n)] if n > 0 else 0.0
        p99 = sorted_data[int(0.99 * n)] if n > 0 else 0.0
        
        return StatisticalSummary(
            mean=mean,
            median=median,
            std_dev=std_dev,
            min_val=sorted_data[0],
            max_val=sorted_data[-1],
            p90=p90,
            p95=p95,
            p99=p99,
            confidence_interval_95=cls._compute_ci(data, mean, std_dev)
        )


class BenchmarkRunner:
    """Executes a benchmark definition concurrently against a target system."""
    
    def __init__(self, target_function: Callable[[Any], Any]):
        """
        Args:
            target_function: An async function that takes an input payload and returns a model output.
        """
        self.target_function = target_function
        self.logger = logging.getLogger("BenchmarkRunner")

    async def _process_item(self, item: DatasetItem, evaluators: List[Any], semaphore: asyncio.Semaphore) -> ItemResult:
        """Processes a single dataset item with concurrency limits."""
        async with semaphore:
            start_time = time.perf_counter()
            error_msg = None
            success = False
            model_output = None
            
            try:
                # In a real system, timeout is enforced here
                model_output = await self.target_function(item.input_payload)
                success = True
            except Exception as e:
                self.logger.error(f"Error processing item {item.item_id}: {e}")
                error_msg = str(e)
                
            duration = (time.perf_counter() - start_time) * 1000
            
            metrics = ExecutionMetrics(
                duration_ms=duration,
                success=success,
                error_msg=error_msg
            )
            
            eval_scores = {}
            if success:
                # Mock evaluation loop - in reality, calls the EvaluatorRegistry
                for eval_name in evaluators:
                    # Mocking the evaluator returning a float
                    eval_scores[eval_name] = 1.0 if str(item.expected_output) in str(model_output) else 0.0
                    
            return ItemResult(
                item_id=item.item_id,
                metrics=metrics,
                evaluator_scores=eval_scores
            )

    async def run(self, definition: BenchmarkDefinition) -> BenchmarkResult:
        """Executes the benchmark definition."""
        self.logger.info(f"Starting benchmark {definition.benchmark_id} with {len(definition.dataset)} items")
        semaphore = asyncio.Semaphore(definition.parallelism)
        
        tasks = [
            self._process_item(item, definition.evaluator_names, semaphore)
            for item in definition.dataset
        ]
        
        results = await asyncio.gather(*tasks)
        
        successful_items = sum(1 for r in results if r.metrics.success)
        failed_items = len(results) - successful_items
        
        timing_data = [r.metrics.duration_ms for r in results if r.metrics.success]
        timing_stats = StatisticalAnalyzer.analyze(timing_data)
        
        accuracy_stats = {}
        for eval_name in definition.evaluator_names:
            scores = [r.evaluator_scores.get(eval_name, 0.0) for r in results if r.metrics.success]
            accuracy_stats[eval_name] = StatisticalAnalyzer.analyze(scores)
            
        return BenchmarkResult(
            run_id=f"run_{datetime.utcnow().timestamp()}",
            benchmark_id=definition.benchmark_id,
            total_items=len(definition.dataset),
            successful_items=successful_items,
            failed_items=failed_items,
            item_results=list(results),
            timing_stats=timing_stats,
            accuracy_stats=accuracy_stats
        )


class BenchmarkComparator:
    """Compares benchmark results across different models or versions."""
    
    @staticmethod
    def _compute_p_value(stat1: StatisticalSummary, n1: int, stat2: StatisticalSummary, n2: int) -> float:
        """Approximates a two-sample t-test p-value for demonstration purposes."""
        if n1 < 2 or n2 < 2:
            return 1.0
        # Welch's t-test approximation
        var1 = stat1.std_dev ** 2
        var2 = stat2.std_dev ** 2
        se = math.sqrt((var1 / n1) + (var2 / n2))
        if se == 0.0:
            return 1.0
        t_stat = abs(stat1.mean - stat2.mean) / se
        # Very rough approximation: if t > 1.96, p < 0.05
        return 0.05 if t_stat > 1.96 else 0.5

    @classmethod
    def compare(cls, baseline: BenchmarkResult, candidate: BenchmarkResult) -> Dict[str, Any]:
        """Compares baseline and candidate benchmark results."""
        comparison = {
            "timing": {
                "baseline_mean_ms": baseline.timing_stats.mean,
                "candidate_mean_ms": candidate.timing_stats.mean,
                "delta_ms": candidate.timing_stats.mean - baseline.timing_stats.mean,
                "p_value": cls._compute_p_value(
                    baseline.timing_stats, baseline.successful_items,
                    candidate.timing_stats, candidate.successful_items
                )
            },
            "accuracy": {},
            "throughput_improvement_percent": 0.0
        }
        
        if baseline.timing_stats.mean > 0:
            speedup = (baseline.timing_stats.mean - candidate.timing_stats.mean) / baseline.timing_stats.mean
            comparison["throughput_improvement_percent"] = speedup * 100
            
        for eval_name in baseline.accuracy_stats.keys():
            if eval_name in candidate.accuracy_stats:
                b_stat = baseline.accuracy_stats[eval_name]
                c_stat = candidate.accuracy_stats[eval_name]
                
                comparison["accuracy"][eval_name] = {
                    "baseline_mean": b_stat.mean,
                    "candidate_mean": c_stat.mean,
                    "delta": c_stat.mean - b_stat.mean,
                    "p_value": cls._compute_p_value(
                        b_stat, baseline.successful_items,
                        c_stat, candidate.successful_items
                    )
                }
                
        return comparison

class LeaderboardGenerator:
    """Generates leaderboards based on aggregate benchmark results."""
    
    @staticmethod
    def generate(results: List[BenchmarkResult], primary_metric: str) -> List[Dict[str, Any]]:
        """Ranks benchmark results based on a primary metric."""
        ranked = []
        for res in results:
            score = 0.0
            if primary_metric == "timing":
                # Lower is better, invert score for ranking
                score = -res.timing_stats.mean
            else:
                if primary_metric in res.accuracy_stats:
                    score = res.accuracy_stats[primary_metric].mean
                    
            ranked.append({
                "run_id": res.run_id,
                "benchmark_id": res.benchmark_id,
                "score": score,
                "success_rate": res.successful_items / res.total_items if res.total_items > 0 else 0.0,
                "timestamp": res.timestamp
            })
            
        return sorted(ranked, key=lambda x: x["score"], reverse=True)
