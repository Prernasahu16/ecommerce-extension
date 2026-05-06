# ============================================================
# EXTENSION LAYER — app_extension.py
# Drop-in loader. Does NOT modify existing app/__init__.py.
#
# Usage — add 2 lines to backend/run.py (or after create_app):
#   from app_extension import register_extensions
#   register_extensions(app)
# ============================================================

import logging
log = logging.getLogger(__name__)


def register_extensions(app):
    """Register all extension blueprints and background jobs."""

    # 1. API blueprint
    from api.ext_routes import ext_bp
    app.register_blueprint(ext_bp)
    log.info("[Extension] ext_bp registered at /api/ext/")

    # 2. Attach extension scoring job to the existing APScheduler if running
    _attach_scheduler_jobs(app)

    log.info("[Extension] All extension modules loaded")
    return app


def _attach_scheduler_jobs(app):
    """
    If the app's existing APScheduler is accessible, add extension jobs to it.
    Falls back silently if the scheduler is unavailable.
    """
    try:
        from apscheduler.schedulers.background import BackgroundScheduler
        # Retrieve the scheduler that was started in create_app()
        # APScheduler stores it as app._scheduler when started there, or we start a new one.
        scheduler = getattr(app, "_ext_scheduler", None)
        if scheduler is None:
            scheduler = BackgroundScheduler()
            app._ext_scheduler = scheduler

        def _ext_score_job():
            try:
                from ml.advanced_score import compute_advanced_scores
                compute_advanced_scores()
            except Exception as e:
                log.error(f"[ExtScheduler] score job failed: {e}")

        if not scheduler.running:
            scheduler.add_job(_ext_score_job, "interval", hours=2, id="ext_score_job",
                              replace_existing=True)
            scheduler.start()
            log.info("[Extension] Extension scheduler started (score every 2h)")
        else:
            scheduler.add_job(_ext_score_job, "interval", hours=2, id="ext_score_job",
                              replace_existing=True)
            log.info("[Extension] Added ext_score_job to existing scheduler")

    except Exception as e:
        log.warning(f"[Extension] Scheduler attachment skipped: {e}")


def register_price_alert_job(scheduler):
    """Add price-alert scan every 4 hours to the extension scheduler."""
    def _alert_job():
        try:
            from services.price_alert import check_all_alerts
            result = check_all_alerts()
            import logging
            logging.getLogger(__name__).info(
                f"[PriceAlert] Scan: {result['total_alerts']} items at target"
            )
        except Exception as e:
            import logging
            logging.getLogger(__name__).error(f"[PriceAlert] Job failed: {e}")

    try:
        scheduler.add_job(
            _alert_job, "interval", hours=4,
            id="ext_price_alert_job", replace_existing=True
        )
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(f"[PriceAlert] Scheduler add failed: {e}")
