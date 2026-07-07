from django.shortcuts import render, redirect,get_object_or_404
from .models import Task
from django.contrib.auth.decorators import login_required
from django.contrib import messages

@login_required
def task_list(request):
    if request.method == 'POST':
        title = request.POST.get('title')
        category = request.POST.get('category') # UI se category lena
        due_date = request.POST.get('due_date')
        Task.objects.create(user=request.user, title=title, category=category, due_date=due_date)
        return redirect('task_list')
    
    tasks = Task.objects.filter(user=request.user).order_by('due_date')
    return render(request, 'task_manager/tasks.html', {'tasks': tasks})


@login_required
def delete_task(request, task_id):
    Task.objects.get(id=task_id, user=request.user).delete()
    return redirect('task_list')

@login_required
def complete_task(request, task_id):
    # Task ko fetch karein
    task = get_object_or_404(Task, id=task_id, user=request.user)
    
    try:
        # Task ko complete mark karein (Assume 'is_completed' field aapke model mein hai)
        task.is_completed = True 
        task.save()
        messages.success(request, "Task successfully complete ho gaya!")
    except Exception as e:
        # Error handling ensure karein
        messages.error(request, f"Error completing task: {str(e)}")
        
    return redirect('task_list')



@login_required
def edit_task(request, task_id):
    # Task fetch karein
    task = get_object_or_404(Task, id=task_id, user=request.user)
    
    if request.method == 'POST':
        # Form data get karein
        new_title = request.POST.get('title', '').strip()
        new_category = request.POST.get('category')
        new_due_date = request.POST.get('due_date')

        # Basic Validation
        if not new_title or not new_due_date:
            messages.error(request, "Title aur Due Date mandatory hain.")
            return redirect('task_list')

        # Duplicate Check: Kya isi title ka koi aur task usi user ka hai?
        # (Exclude current task from check)
        if Task.objects.filter(user=request.user, title=new_title).exclude(id=task_id).exists():
            messages.error(request, "Yeh task already exist karta hai.")
            return redirect('task_list')

        # Data update karein
        try:
            task.title = new_title
            task.category = new_category
            task.due_date = new_due_date
            task.save()
            messages.success(request, "Task successfully update ho gaya!")
        except Exception as e:
            # Error handling
            messages.error(request, f"Error updating task: {str(e)}")
            
    return redirect('task_list')