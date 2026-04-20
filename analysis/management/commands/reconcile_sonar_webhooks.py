from django.core.management.base import BaseCommand
from analysis.services.sonar_finalize_service import reconcile_stale_waiting_runs

class Command(BaseCommand):
    help = (
        'Intenta finalizar AnalysisRun en WAITING_SONAR_WEBHOOK antiguos usando la API de SonarCloud '
        '(respaldo si falló el webhook). Ejecutar vía cron cada 15–30 minutos en producción.'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--max',
            type=int,
            default=30,
            help='Número máximo de runs a intentar en esta ejecución.',
        )

    def handle(self, *args, **options):
        n = reconcile_stale_waiting_runs(max_runs=int(options['max']))
        self.stdout.write(self.style.SUCCESS(f'Runs finalizados vía reconciliación: {n}'))
