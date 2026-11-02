"""Project billing hours use approved time entries, including workflow tasks."""


def approved_hours(db):
    # Group once by project. Task and project entries each contribute once;
    # estimates, pending entries and corrections never contribute.
    return {r['project_id']:r['minutes']/60 for r in db.execute('''
      SELECT u.project_id,SUM(u.minutes) AS minutes FROM updates u
      JOIN items p ON p.id=u.project_id AND p.type='project'
      WHERE u.time_status='approved' GROUP BY u.project_id''')}
