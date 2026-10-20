import re
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.db import connection
from django.utils import timezone

from apps.tasks.models import Project, Task, TaskPriority, TaskStatus, User


class Command(BaseCommand):
    help = "Demonstrates PostgreSQL EXPLAIN ANALYZE comparison before and after Index optimization."

    def add_arguments(self, parser):
        parser.add_argument(
            "--count",
            type=int,
            default=10000,
            help="Number of tasks to generate for the benchmark (default: 10000)",
        )
        parser.add_argument(
            "--cleanup",
            action="store_true",
            help="Clean up generated benchmark tasks after the run",
        )

    def handle(self, *args, **options):
        count = options["count"]
        cleanup = options["cleanup"]

        self.stdout.write(self.style.MIGRATE_HEADING("=== PostgreSQL Query Optimization Benchmark (EXPLAIN ANALYZE) ==="))

        # Ensure benchmark user and project exist
        user, _ = User.objects.get_or_create(
            username="benchmark_user",
            defaults={"email": "bench@example.com", "first_name": "Bench", "last_name": "Tester"},
        )
        project, _ = Project.objects.get_or_create(
            name="Benchmark Project",
            defaults={"description": "Project for EXPLAIN ANALYZE benchmarking", "owner": user},
        )

        current_count = Task.objects.count()
        generated = False
        if current_count < count:
            needed = count - current_count
            self.stdout.write(f"Populating database with {needed} benchmark tasks...")
            now = timezone.now()
            batch_size = 2000
            tasks = []
            for i in range(needed):
                tasks.append(
                    Task(
                        title=f"Benchmark Task #{i + current_count}",
                        description="Load testing task index performance",
                        status=TaskStatus.TODO if i % 2 == 0 else TaskStatus.DONE,
                        priority=TaskPriority.HIGH if i % 3 == 0 else TaskPriority.LOW,
                        project=project,
                        assignee=user,
                        due_date=now + timedelta(days=(i % 40) - 10),
                    )
                )
                if len(tasks) >= batch_size:
                    Task.objects.bulk_create(tasks)
                    tasks.clear()
            if tasks:
                Task.objects.bulk_create(tasks)
            generated = True
            self.stdout.write(self.style.SUCCESS(f"Successfully generated {needed} tasks. Total in DB: {Task.objects.count()}"))
        else:
            self.stdout.write(f"Using existing {current_count} tasks in database.")

        with connection.cursor() as cursor:
            # Update PostgreSQL optimizer statistics
            cursor.execute("ANALYZE tasks_task;")

            query_sql = """
                SELECT id, title, status, due_date
                FROM tasks_task
                WHERE status = 'todo' AND due_date <= NOW() + INTERVAL '5 days';
            """

            # 1. Sequential Scan (simulate query without index)
            cursor.execute("SET enable_indexscan = off;")
            cursor.execute("SET enable_bitmapscan = off;")
            cursor.execute(f"EXPLAIN (ANALYZE, BUFFERS) {query_sql}")
            seq_plan_rows = [row[0] for row in cursor.fetchall()]

            # 2. Index Scan (with composite index task_status_due_date_idx)
            cursor.execute("SET enable_indexscan = on;")
            cursor.execute("SET enable_bitmapscan = on;")
            cursor.execute(f"EXPLAIN (ANALYZE, BUFFERS) {query_sql}")
            idx_plan_rows = [row[0] for row in cursor.fetchall()]

            # Reset settings
            cursor.execute("RESET enable_indexscan;")
            cursor.execute("RESET enable_bitmapscan;")

        self.stdout.write("\n" + self.style.WARNING("--- 1. EXPLAIN ANALYZE: Sequential Scan (Without Index) ---"))
        for line in seq_plan_rows:
            self.stdout.write(f"  {line}")

        self.stdout.write("\n" + self.style.SUCCESS("--- 2. EXPLAIN ANALYZE: Index Scan (With task_status_due_date_idx) ---"))
        for line in idx_plan_rows:
            self.stdout.write(f"  {line}")

        # Parse execution times
        def extract_time(rows):
            for row in rows:
                match = re.search(r"Execution Time:\s*([\d\.]+)\s*ms", row)
                if match:
                    return float(match.group(1))
            return None

        seq_time = extract_time(seq_plan_rows)
        idx_time = extract_time(idx_plan_rows)

        self.stdout.write("\n" + self.style.MIGRATE_HEADING("=== Performance Summary ==="))
        if seq_time is not None and idx_time is not None:
            self.stdout.write(f"Sequential Scan Execution Time: {seq_time:.3f} ms")
            self.stdout.write(f"Index Scan Execution Time:      {idx_time:.3f} ms")
            speedup = (seq_time / idx_time) if idx_time > 0 else 1.0
            self.stdout.write(self.style.SUCCESS(f"Performance Speedup:           {speedup:.2f}x faster with Index!"))

        if cleanup and generated:
            self.stdout.write("Cleaning up benchmark data...")
            Task.objects.filter(project=project).delete()
            project.delete()
            user.delete()
            self.stdout.write(self.style.SUCCESS("Cleanup completed."))
