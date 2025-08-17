from flask import Flask, render_template, request, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
import os
from datetime import date, datetime, timedelta
from collections import Counter

app = Flask(__name__)
app.secret_key = '1916'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///todo.db'
db = SQLAlchemy(app)
migrate = Migrate(app, db)  # <-- This line is required

class Task(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    task = db.Column(db.String(200), nullable=False)
    completed = db.Column(db.Boolean, default=False)
    priority = db.Column(db.String(10), default="Medium")
    due_date = db.Column(db.Date, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    completed_at = db.Column(db.DateTime, nullable=True)

@app.route('/', methods=['GET'])
def index():
    priority_order = {'High': 1, 'Medium': 2, 'Low': 3}
    # Filtering, sorting, and search
    status = request.args.get('status', 'all')
    sort = request.args.get('sort', 'priority')
    search = request.args.get('search', '').strip()
    query = Task.query
    if status == 'completed':
        query = query.filter_by(completed=True)
    elif status == 'pending':
        query = query.filter_by(completed=False)
    if search:
        query = query.filter(Task.task.ilike(f'%{search}%'))
    if sort == 'priority':
        tasks = sorted(query.all(), key=lambda t: (priority_order[t.priority], t.completed))
    elif sort == 'due_date':
        tasks = sorted(query.all(), key=lambda t: (t.due_date or '9999-12-31', t.completed))
    elif sort == 'created':
        tasks = sorted(query.all(), key=lambda t: t.id)
    else:
        tasks = query.all()
    completed_count = sum(1 for t in tasks if t.completed)
    percent = int((completed_count / len(tasks)) * 100) if tasks else 0
    # --- Notification data (overdue, due today, due soon) ---
    today_date = date.today()
    soon_threshold = today_date + timedelta(days=1)
    pending_tasks = Task.query.filter_by(completed=False).all()
    overdue_tasks = [t for t in pending_tasks if t.due_date and t.due_date < today_date]
    due_today_tasks = [t for t in pending_tasks if t.due_date and t.due_date == today_date]
    due_soon_tasks = [t for t in pending_tasks if t.due_date and today_date < t.due_date <= soon_threshold]
    notify_tasks = [
        {"id": t.id, "task": t.task, "due_date": t.due_date.isoformat(), "type": "overdue"}
        for t in overdue_tasks
    ] + [
        {"id": t.id, "task": t.task, "due_date": t.due_date.isoformat(), "type": "today"}
        for t in due_today_tasks
    ] + [
        {"id": t.id, "task": t.task, "due_date": t.due_date.isoformat(), "type": "soon"}
        for t in due_soon_tasks
    ]
    return render_template(
        'index.html',
        tasks=tasks,
        percent=percent,
        status=status,
        sort=sort,
        search=search,
        today=today_date,
        soon_threshold=soon_threshold,
        num_overdue=len(overdue_tasks),
        num_due_today=len(due_today_tasks),
        num_due_soon=len(due_soon_tasks),
        notify_tasks=notify_tasks,
    )


@app.route('/add', methods=['POST'])
def add():
    task_content = request.form['task']
    priority = request.form['priority']
    due_date = request.form.get('due_date')

    if due_date:
        due_date = datetime.strptime(due_date, '%Y-%m-%d').date()
        # ✅ Prevent past dates
        if due_date < date.today():
            flash('Due date cannot be in the past!', 'danger')
            return redirect(url_for('index'))
    else:
        due_date = None

    if task_content:
        new_task = Task(task=task_content, priority=priority, due_date=due_date, created_at=datetime.utcnow())
        db.session.add(new_task)
        db.session.commit()

    return redirect(url_for('index'))




@app.route('/complete/<int:id>')
def complete(id):
    task = Task.query.get_or_404(id)
    task.completed = not task.completed
    if task.completed:
        task.completed_at = datetime.utcnow()
    else:
        task.completed_at = None
    db.session.commit()
    return redirect(url_for('index'))

@app.route('/delete/<int:id>')
def delete(id):
    task = Task.query.get_or_404(id)
    db.session.delete(task)
    db.session.commit()
    return redirect(url_for('index'))

@app.route('/edit/<int:task_id>', methods=['GET', 'POST'])
def edit(task_id):
    task = Task.query.get_or_404(task_id)

    if request.method == 'POST':
        task.task = request.form['task']
        task.priority = request.form['priority']
        due_date = request.form.get('due_date')

        if due_date:
            due_date = datetime.strptime(due_date, '%Y-%m-%d').date()
            # ✅ Prevent past dates
            if due_date < date.today():
                flash('Due date cannot be in the past!', 'danger')
                return redirect(url_for('edit', task_id=task_id))
            task.due_date = due_date
        else:
            task.due_date = None

        db.session.commit()
        flash('Task updated successfully!', 'success')
        return redirect(url_for('index'))

    return render_template('edit.html', task=task)

@app.route('/dashboard')
def dashboard():
    total_tasks = Task.query.count()
    completed_tasks = Task.query.filter_by(completed=True).count()
    incomplete_tasks = total_tasks - completed_tasks

    # Priority distribution
    priorities = ['High', 'Medium', 'Low']
    priority_data = {
        priority: Task.query.filter_by(priority=priority).count()
        for priority in priorities
    }

    # --- Progress Analytics ---
    # 1. Completions per day (last 7 days)
    from datetime import timedelta
    today = date.today()
    last_7_days = [today - timedelta(days=i) for i in range(6, -1, -1)]
    completions = Task.query.filter(Task.completed_at != None).all()
    completions_per_day = Counter(
        (t.completed_at.date() for t in completions if t.completed_at)
    )
    completions_chart = [completions_per_day.get(day, 0) for day in last_7_days]
    completions_labels = [day.strftime('%a') for day in last_7_days]

    # 2. Completion rate
    completion_rate = int((completed_tasks / total_tasks) * 100) if total_tasks else 0

    # 3. Streak (consecutive days with at least one completion)
    streak = 0
    for day in reversed(last_7_days):
        if completions_per_day.get(day, 0) > 0:
            streak += 1
        else:
            break

    # 4. Average completion time (in hours)
    completion_times = [
        (t.completed_at - t.created_at).total_seconds() / 3600
        for t in completions if t.completed_at and t.created_at
    ]
    avg_completion_time = round(sum(completion_times) / len(completion_times), 1) if completion_times else None

    return render_template(
        'dashboard.html',
        total=total_tasks,
        completed=completed_tasks,
        incomplete=incomplete_tasks,
        priority_data=priority_data,
        completions_chart=completions_chart,
        completions_labels=completions_labels,
        completion_rate=completion_rate,
        streak=streak,
        avg_completion_time=avg_completion_time
    )

@app.route('/completed-tasks')
def completed_tasks():
    # Get all completed tasks, sorted by completion date (most recent first)
    completed_tasks = Task.query.filter_by(completed=True).order_by(Task.completed_at.desc()).all()
    
    # Calculate some statistics for the completed tasks page
    total_completed = len(completed_tasks)
    
    # Calculate completed today and this week
    today = date.today()
    week_start = today - timedelta(days=today.weekday())
    week_end = week_start + timedelta(days=6)
    
    completed_today = 0
    completed_this_week = 0
    
    for task in completed_tasks:
        if task.completed_at:
            completion_date = task.completed_at.date()
            if completion_date == today:
                completed_today += 1
            if week_start <= completion_date <= week_end:
                completed_this_week += 1
    
    return render_template(
        'completed_tasks.html',
        completed_tasks=completed_tasks,
        total_completed=total_completed,
        completed_today=completed_today,
        completed_this_week=completed_this_week,
        today=today
    )

@app.route('/incomplete-tasks')
def incomplete_tasks():
    try:
        # Get all incomplete tasks
        incomplete_tasks = Task.query.filter_by(completed=False).all()
        print(f"Found {len(incomplete_tasks)} incomplete tasks")
        
        # If no incomplete tasks, show empty state
        if not incomplete_tasks:
            return render_template(
                'incomplete_tasks.html',
                incomplete_tasks=[],
                total_incomplete=0,
                overdue_tasks=0,
                due_today_tasks=0,
                due_soon_tasks=0,
                today=date.today(),
                soon_threshold=date.today() + timedelta(days=1)
            )
        
        # Calculate some statistics for the incomplete tasks page
        total_incomplete = len(incomplete_tasks)
        
        # Calculate overdue and due soon tasks
        today = date.today()
        soon_threshold = today + timedelta(days=1)
        
        overdue_tasks = 0
        due_today_tasks = 0
        due_soon_tasks = 0
        
        for task in incomplete_tasks:
            if task.due_date:
                if task.due_date < today:
                    overdue_tasks += 1
                elif task.due_date == today:
                    due_today_tasks += 1
                elif task.due_date <= soon_threshold:
                    due_soon_tasks += 1
        
        # Sort tasks by priority (High first) and then by due date (earliest first)
        priority_order = {'High': 1, 'Medium': 2, 'Low': 3}
        incomplete_tasks = sorted(incomplete_tasks, key=lambda t: (priority_order.get(t.priority, 4), t.due_date or date.max))
        
        print(f"Rendering template with {len(incomplete_tasks)} tasks")
        
        return render_template(
            'incomplete_tasks.html',
            incomplete_tasks=incomplete_tasks,
            total_incomplete=total_incomplete,
            overdue_tasks=overdue_tasks,
            due_today_tasks=due_today_tasks,
            due_soon_tasks=due_soon_tasks,
            today=today,
            soon_threshold=soon_threshold
        )
    except Exception as e:
        # Log the error and return a simple error page
        print(f"Error in incomplete_tasks route: {e}")
        import traceback
        traceback.print_exc()
        flash('An error occurred while loading incomplete tasks.', 'danger')
        return redirect(url_for('index'))

@app.route('/debug-tasks')
def debug_tasks():
    try:
        total_tasks = Task.query.count()
        completed_tasks = Task.query.filter_by(completed=True).count()
        incomplete_tasks = Task.query.filter_by(completed=False).count()
        
        # Get a few sample tasks
        sample_tasks = Task.query.limit(5).all()
        
        debug_info = {
            'total_tasks': total_tasks,
            'completed_tasks': completed_tasks,
            'incomplete_tasks': incomplete_tasks,
            'sample_tasks': [
                {
                    'id': task.id,
                    'task': task.task,
                    'completed': task.completed,
                    'priority': task.priority,
                    'due_date': str(task.due_date) if task.due_date else None
                }
                for task in sample_tasks
            ]
        }
        
        return f"""
        <h1>Debug Information</h1>
        <p>Total tasks: {total_tasks}</p>
        <p>Completed tasks: {completed_tasks}</p>
        <p>Incomplete tasks: {incomplete_tasks}</p>
        <h2>Sample Tasks:</h2>
        <pre>{debug_info}</pre>
        """
    except Exception as e:
        return f"Error: {e}"

if __name__ == '__main__':
    if not os.path.exists('todo.db'):
        with app.app_context():
            db.create_all()

    import os
    port = int(os.environ.get('PORT', 5000))  # fallback to 5000 locally
    app.run(host='0.0.0.0', port=port)