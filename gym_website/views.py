from django.views.generic import TemplateView

class IndexView(TemplateView):
    template_name = 'gym_website/index.html'

class AboutView(TemplateView):
    template_name = 'gym_website/about.html'

class ContactView(TemplateView):
    template_name = 'gym_website/contact.html'

class EventsView(TemplateView):
    template_name = 'gym_website/events.html'

class NotificationsView(TemplateView):
    template_name = 'gym_website/notifications.html'

class ProgramsView(TemplateView):
    template_name = 'gym_website/programs.html'

class TrainersView(TemplateView):
    template_name = 'gym_website/trainers.html'

class TechView(TemplateView):
    template_name = 'gym_website/tech.html'
