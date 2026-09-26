import asyncio
from enum import Enum
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field, ConfigDict
import time

class MetricType(str, Enum):
    COUNTER = "counter"
    GAUGE = "gauge"
    HISTOGRAM = "histogram"

class AlertSeverity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"

class MonitoringMetric(BaseModel):
    model_config = ConfigDict(strict=True)
    name: str
    type: MetricType
    value: float
    threshold: Optional[float] = None
    alert_policy: Optional[AlertSeverity] = None

class MetricsCollector:
    """Buffered async writes for metrics."""
    def __init__(self, buffer_size: int = 100):
        self.buffer_size = buffer_size
        self.buffer: List[MonitoringMetric] = []
        
    async def record(self, metric: MonitoringMetric):
        self.buffer.append(metric)
        if len(self.buffer) >= self.buffer_size:
            await self.flush()
            
    async def flush(self):
        await asyncio.sleep(0.05)
        self.buffer.clear()

class AlertEngine:
    """Severity-based routing."""
    def route_alert(self, metric: MonitoringMetric, message: str):
        if metric.alert_policy == AlertSeverity.CRITICAL:
            print(f"CRITICAL ALERT [Paging OnCall]: {message}")
        elif metric.alert_policy == AlertSeverity.WARNING:
            print(f"WARNING ALERT [Slack]: {message}")
        else:
            print(f"INFO: {message}")

class DashboardData(BaseModel):
    model_config = ConfigDict(strict=True)
    title: str
    panels: List[Dict[str, Any]]

class IncidentDetector:
    """Automated issue detection."""
    def __init__(self, alert_engine: AlertEngine):
        self.alert_engine = alert_engine
        
    def check_metric(self, metric: MonitoringMetric):
        if metric.threshold is not None:
            if metric.value > metric.threshold:
                self.alert_engine.route_alert(
                    metric, 
                    f"Metric {metric.name} exceeded threshold: {metric.value} > {metric.threshold}"
                )

class MonitoringReport(BaseModel):
    model_config = ConfigDict(strict=True)
    active_incidents: int
    metrics_collected: int
    system_health_score: float

class MonitoringSystem:
    def __init__(self):
        self.collector = MetricsCollector()
        self.alert_engine = AlertEngine()
        self.detector = IncidentDetector(self.alert_engine)
        
    async def process_metric(self, metric: MonitoringMetric):
        await self.collector.record(metric)
        self.detector.check_metric(metric)
