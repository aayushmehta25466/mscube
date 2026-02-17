"""
Django management command to populate test data for MScube Gym Management System.

Usage: python manage.py populate_test_data
"""
from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import date, timedelta
from decimal import Decimal
import random

from accounts.models import User, Member, Trainer, Staff, AdminProfile
from gym_management.models import MembershipPlan, Subscription, Payment, Attendance


class Command(BaseCommand):
    help = 'Populates the database with test users and data for all roles'

    def add_arguments(self, parser):
        parser.add_argument(
            '--clear',
            action='store_true',
            help='Clear existing test data before populating',
        )

    def handle(self, *args, **options):
        self.stdout.write(self.style.WARNING('Starting test data population...'))
        
        if options['clear']:
            self.stdout.write(self.style.WARNING('Clearing existing data...'))
            self.clear_data()
        
        # Create users and profiles
        admin_users = self.create_admins()
        staff_users = self.create_staff()
        trainer_users = self.create_trainers()
        member_users = self.create_members()
        
        # Create membership plans
        plans = self.create_membership_plans()
        
        # Create subscriptions and payments for members
        self.create_subscriptions_and_payments(member_users, plans)
        
        # Create attendance records
        self.create_attendance_records(member_users)
        
        # Save credentials to file
        self.save_credentials_to_file(admin_users, staff_users, trainer_users, member_users)
        
        self.stdout.write(self.style.SUCCESS('\n' + '='*60))
        self.stdout.write(self.style.SUCCESS('Test data population completed!'))
        self.stdout.write(self.style.SUCCESS('='*60))
        self.print_summary(admin_users, staff_users, trainer_users, member_users)
    
    def clear_data(self):
        """Clear existing test data."""
        Attendance.objects.all().delete()
        Payment.objects.all().delete()
        Subscription.objects.all().delete()
        MembershipPlan.objects.all().delete()
        
        Member.objects.all().delete()
        Trainer.objects.all().delete()
        Staff.objects.all().delete()
        AdminProfile.objects.all().delete()
        
        # Delete non-superuser users
        User.objects.filter(is_superuser=False).delete()
        
        self.stdout.write(self.style.SUCCESS('✓ Existing data cleared'))
    
    def create_admins(self):
        """Create admin users."""
        admins_data = [
            {
                'email': 'admin@mscube.com',
                'full_name': 'Admin User',
                'username': 'mscube_admin',
                'phone': '+9779801234567',
                'dob': date(1985, 5, 15),
                'address': 'House No. 25, Durbarmarg, Kathmandu 44600, Nepal',
                'can_manage_users': True,
                'can_manage_payments': True,
                'can_view_reports': True,
            },
            {
                'email': 'admin2@mscube.com',
                'full_name': 'Rajesh Kumar',
                'username': 'rajesh_admin',
                'phone': '+9779801234590',
                'dob': date(1982, 9, 20),
                'address': 'Lakeside-6, Baidam Road, Pokhara 33700, Nepal',
                'can_manage_users': True,
                'can_manage_payments': True,
                'can_view_reports': True,
            },
            {
                'email': 'admin3@mscube.com',
                'full_name': 'Anita Shrestha',
                'username': 'anita_admin',
                'phone': '+9779801234591',
                'dob': date(1987, 2, 14),
                'address': 'Jawalakhel-15, Kumaripati, Lalitpur 44700, Nepal',
                'can_manage_users': False,
                'can_manage_payments': True,
                'can_view_reports': True,
            },
        ]
        
        created_admins = []
        for admin_data in admins_data:
            user, created = User.objects.get_or_create(
                email=admin_data['email'],
                defaults={
                    'full_name': admin_data['full_name'],
                    'username': admin_data['username'],
                    'phone': admin_data['phone'],
                    'is_verified': True,
                    'is_staff': True,
                }
            )
            if created:
                user.set_password('Admin@123')
                user.save()
                
                AdminProfile.objects.create(
                    user=user,
                    date_of_birth=admin_data['dob'],
                    address=admin_data['address'],
                    can_manage_users=admin_data['can_manage_users'],
                    can_manage_payments=admin_data['can_manage_payments'],
                    can_view_reports=admin_data['can_view_reports'],
                )
                self.stdout.write(self.style.SUCCESS(f'✓ Admin created: {admin_data["full_name"]}'))
            else:
                self.stdout.write(self.style.WARNING(f'⚠ Admin already exists: {admin_data["full_name"]}'))
            
            created_admins.append(user)
        
        return created_admins
    
    def create_staff(self):
        """Create staff users."""
        staff_data = [
            {
                'email': 'staff@mscube.com',
                'full_name': 'Sarah Johnson',
                'username': 'sarah_staff',
                'phone': '+9779801234568',
                'dob': date(1992, 8, 22),
                'address': 'Sanepa-2, Ward No. 3, Lalitpur 44600, Nepal',
                'department': 'Front Desk',
            },
            {
                'email': 'staff2@mscube.com',
                'full_name': 'Bikram Thapa',
                'username': 'bikram_staff',
                'phone': '+9779801234592',
                'dob': date(1995, 3, 8),
                'address': 'Chabahil-4, Near Pashupatinath Temple, Kathmandu 44600, Nepal',
                'department': 'Maintenance',
            },
            {
                'email': 'staff3@mscube.com',
                'full_name': 'Priya Gurung',
                'username': 'priya_staff',
                'phone': '+9779801234593',
                'dob': date(1993, 11, 15),
                'address': 'Durbar Square, Bhaktapur 44800, Nepal',
                'department': 'Sales',
            },
            {
                'email': 'staff4@mscube.com',
                'full_name': 'Suresh Tamang',
                'username': 'suresh_staff',
                'phone': '+9779801234594',
                'dob': date(1990, 6, 30),
                'address': 'Naya Bazar-12, Kirtipur Municipality, Kathmandu 44618, Nepal',
                'department': 'Front Desk',
            },
        ]
        
        created_staff = []
        for staff_info in staff_data:
            user, created = User.objects.get_or_create(
                email=staff_info['email'],
                defaults={
                    'full_name': staff_info['full_name'],
                    'username': staff_info['username'],
                    'phone': staff_info['phone'],
                    'is_verified': True,
                }
            )
            if created:
                user.set_password('Staff@123')
                user.save()
                
                Staff.objects.create(
                    user=user,
                    date_of_birth=staff_info['dob'],
                    address=staff_info['address'],
                    department=staff_info['department'],
                )
                self.stdout.write(self.style.SUCCESS(f'✓ Staff created: {staff_info["full_name"]}'))
            else:
                self.stdout.write(self.style.WARNING(f'⚠ Staff already exists: {staff_info["full_name"]}'))
            
            created_staff.append(user)
        
        return created_staff
    
    def create_trainers(self):
        """Create trainer users."""
        trainers_data = [
            {
                'email': 'trainer1@mscube.com',
                'full_name': 'John Smith',
                'username': 'john_trainer',
                'phone': '+9779801234569',
                'dob': date(1988, 3, 10),
                'address': 'Thimi-5, Near Balkumari Temple, Bhaktapur 44800, Nepal',
                'specialization': 'Weight Training & Bodybuilding',
                'experience_years': 8,
                'bio': 'ISSA Certified Personal Trainer with 8+ years experience. Former competitive bodybuilder (Mr. Nepal 2018 finalist). Specializes in strength training, muscle hypertrophy, and competition preparation. Expert in nutrition planning, supplement guidance, and progressive overload training techniques. Successfully trained 100+ clients in achieving their physique goals.',
            },
            {
                'email': 'trainer2@mscube.com',
                'full_name': 'Maya Rai',
                'username': 'maya_trainer',
                'phone': '+9779801234570',
                'dob': date(1990, 7, 18),
                'address': 'Mangal Bazar-21, Patan Durbar Square, Lalitpur 44700, Nepal',
                'specialization': 'Yoga & Flexibility Training',
                'experience_years': 5,
                'bio': 'RYT-500 Certified Yoga Alliance Instructor. Specializes in Hatha, Vinyasa, and Ashtanga yoga. Trained in India (Rishikesh) with advanced certifications in pranayama and meditation. Conducts therapeutic yoga sessions for stress relief, flexibility improvement, and injury rehabilitation. Regular classes include morning flow, power yoga, and restorative evening sessions.',
            },
            {
                'email': 'trainer3@mscube.com',
                'full_name': 'Rajiv Maharjan',
                'username': 'rajiv_trainer',
                'phone': '+9779801234595',
                'dob': date(1986, 12, 5),
                'address': 'Lagankhel-8, Near Bus Park, Lalitpur 44700, Nepal',
                'specialization': 'CrossFit & HIIT',
                'experience_years': 7,
                'bio': 'CrossFit Level 2 Certified Trainer (CF-L2). Specializes in high-intensity interval training, Olympic weightlifting, and functional fitness. Former military fitness instructor with expertise in metabolic conditioning and group training. Designs challenging WODs (Workouts of the Day) focused on strength, endurance, and agility. Holds additional certifications in kettlebell training and battle rope techniques.',
            },
            {
                'email': 'trainer4@mscube.com',
                'full_name': 'Deepa Lama',
                'username': 'deepa_trainer',
                'phone': '+9779801234596',
                'dob': date(1991, 4, 22),
                'address': 'Boudhanath-3, Near Stupa, Kathmandu 44600, Nepal',
                'specialization': 'Pilates & Core Strength',
                'experience_years': 4,
                'bio': 'Comprehensively certified Pilates instructor (Classical & Contemporary). Specializes in mat Pilates, reformer work, and rehabilitation exercises. Works closely with physiotherapists for post-injury recovery programs. Expert in core stability, postural correction, and lower back pain management. Trained in prenatal and postnatal Pilates. Personalized sessions focus on flexibility, balance, and functional strength.',
            },
            {
                'email': 'trainer5@mscube.com',
                'full_name': 'Aditya Singh',
                'username': 'aditya_trainer',
                'phone': '+9779801234597',
                'dob': date(1989, 8, 17),
                'address': 'Thankot-11, Nepal-India Highway, Kathmandu 44600, Nepal',
                'specialization': 'Sports Performance & Athletic Training',
                'experience_years': 6,
                'bio': 'NSCA Certified Strength & Conditioning Specialist (CSCS). Former national-level track and field athlete. Specializes in sports-specific training, speed and agility development, plyometric exercises, and SAQ (Speed, Agility, Quickness) drills. Works with athletes from football, basketball, cricket, and martial arts. Expert in injury prevention, movement mechanics, and performance optimization through periodized training programs.',
            },
        ]
        
        created_trainers = []
        for trainer_data in trainers_data:
            user, created = User.objects.get_or_create(
                email=trainer_data['email'],
                defaults={
                    'full_name': trainer_data['full_name'],
                    'username': trainer_data['username'],
                    'phone': trainer_data['phone'],
                    'is_verified': True,
                }
            )
            if created:
                user.set_password('Trainer@123')
                user.save()
                
                Trainer.objects.create(
                    user=user,
                    date_of_birth=trainer_data['dob'],
                    address=trainer_data['address'],
                    specialization=trainer_data['specialization'],
                    experience_years=trainer_data['experience_years'],
                    bio=trainer_data['bio'],
                )
                self.stdout.write(self.style.SUCCESS(f'✓ Trainer created: {trainer_data["full_name"]}'))
            else:
                self.stdout.write(self.style.WARNING(f'⚠ Trainer already exists: {trainer_data["full_name"]}'))
            
            created_trainers.append(user)
        
        return created_trainers
    
    def create_members(self):
        """Create member users."""
        members_data = [
            {
                'email': 'member1@example.com',
                'full_name': 'Raj Sharma',
                'username': 'raj_member',
                'phone': '+9779801234571',
                'dob': date(1995, 4, 12),
                'address': 'Thamel-26, Near Kathmandu Guest House, Kathmandu 44600, Nepal',
                'emergency_contact': 'Sunita Sharma (Mother) - +9779801111111',
            },
            {
                'email': 'member2@example.com',
                'full_name': 'Priya Patel',
                'username': 'priya_member',
                'phone': '+9779801234572',
                'dob': date(1998, 9, 25),
                'address': 'Baneshwor-34, Near Minbhawan, Kathmandu 44600, Nepal',
                'emergency_contact': 'Ramesh Patel (Father) - +9779802222222',
            },
            {
                'email': 'member3@example.com',
                'full_name': 'Amit Kumar',
                'username': 'amit_member',
                'phone': '+9779801234573',
                'dob': date(1993, 1, 8),
                'address': 'Koteshwor-17, Near Bus Stop, Kathmandu 44600, Nepal',
                'emergency_contact': 'Anjali Kumar (Wife) - +9779803333333',
            },
            {
                'email': 'member4@example.com',
                'full_name': 'Sita Devi',
                'username': 'sita_member',
                'phone': '+9779801234574',
                'dob': date(2000, 11, 30),
                'address': 'Pulchowk-9, Lalitpur Engineering Campus Area, Lalitpur 44700, Nepal',
                'emergency_contact': 'Kiran Devi (Brother) - +9779804444444',
            },
            {
                'email': 'member5@example.com',
                'full_name': 'Ramesh Thapa',
                'username': 'ramesh_member',
                'phone': '+9779801234575',
                'dob': date(1987, 6, 14),
                'address': 'Bagbazar-5, Near Tundikhel, Kathmandu 44600, Nepal',
                'emergency_contact': 'Sarita Thapa (Wife) - +9779805555555',
            },
        ]
        
        created_members = []
        for member_data in members_data:
            user, created = User.objects.get_or_create(
                email=member_data['email'],
                defaults={
                    'full_name': member_data['full_name'],
                    'username': member_data['username'],
                    'phone': member_data['phone'],
                    'is_verified': True,
                }
            )
            if created:
                user.set_password('Member@123')
                user.save()
                
                Member.objects.create(
                    user=user,
                    date_of_birth=member_data['dob'],
                    address=member_data['address'],
                    emergency_contact=member_data['emergency_contact'],
                )
                self.stdout.write(self.style.SUCCESS(f'✓ Member created: {member_data["full_name"]}'))
            else:
                self.stdout.write(self.style.WARNING(f'⚠ Member already exists: {member_data["full_name"]}'))
            
            created_members.append(user)
        
        return created_members
    
    def create_membership_plans(self):
        """Create membership plans."""
        plans_data = [
            {
                'name': 'Basic Monthly',
                'description': 'Perfect for beginners who want to maintain a regular fitness routine.',
                'price': Decimal('2500.00'),
                'duration_days': 30,
                'features': 'Access to gym facilities\nCardio equipment\nFree weights\nLocker facility\nShower access',
            },
            {
                'name': 'Standard Quarterly',
                'description': 'Great value for committed members looking for sustained fitness progress.',
                'price': Decimal('6500.00'),
                'duration_days': 90,
                'features': 'All Basic features\n1 complimentary training session\nNutrition consultation\nProgress tracking\nGroup classes access',
            },
            {
                'name': 'Premium Yearly',
                'description': 'Best value plan with all amenities for serious fitness enthusiasts.',
                'price': Decimal('22000.00'),
                'duration_days': 365,
                'features': 'All Standard features\n4 personal training sessions/month\nDiet plan included\nSauna access\nFree gym merchandise\nPriority class bookings',
            },
            {
                'name': 'Student Monthly',
                'description': 'Special discounted plan for students with valid ID.',
                'price': Decimal('1800.00'),
                'duration_days': 30,
                'features': 'Access to gym facilities\nCardio equipment\nFree weights\nLocker facility\nValid student ID required',
            },
        ]
        
        created_plans = []
        for plan_data in plans_data:
            plan, created = MembershipPlan.objects.get_or_create(
                name=plan_data['name'],
                defaults={
                    'description': plan_data['description'],
                    'price': plan_data['price'],
                    'duration_days': plan_data['duration_days'],
                    'features': plan_data['features'],
                    'is_active': True,
                }
            )
            if created:
                self.stdout.write(self.style.SUCCESS(f'✓ Membership plan created: {plan_data["name"]}'))
            else:
                self.stdout.write(self.style.WARNING(f'⚠ Membership plan already exists: {plan_data["name"]}'))
            
            created_plans.append(plan)
        
        return created_plans
    
    def create_subscriptions_and_payments(self, member_users, plans):
        """Create subscriptions and payments for members."""
        for i, member_user in enumerate(member_users):
            member = member_user.member
            
            # Select a random plan
            plan = random.choice(plans)
            
            # Create subscription
            # Mix of active, pending, and expired subscriptions
            if i == 0:  # First member: active subscription
                start_date = date.today() - timedelta(days=15)
                end_date = start_date + timedelta(days=plan.duration_days)
                status = 'active'
            elif i == 1:  # Second member: pending subscription
                start_date = date.today()
                end_date = start_date + timedelta(days=plan.duration_days)
                status = 'pending'
            elif i == 2:  # Third member: expired subscription
                start_date = date.today() - timedelta(days=plan.duration_days + 30)
                end_date = start_date + timedelta(days=plan.duration_days)
                status = 'expired'
            else:  # Rest: active subscriptions
                start_date = date.today() - timedelta(days=random.randint(5, 20))
                end_date = start_date + timedelta(days=plan.duration_days)
                status = 'active'
            
            subscription = Subscription.objects.create(
                member=member,
                plan=plan,
                start_date=start_date,
                end_date=end_date,
                status=status,
            )
            
            # Create payment for subscription
            if status in ['active', 'expired']:
                payment_status = 'completed'
                completed_at = timezone.now() - timedelta(days=random.randint(1, 30))
            else:
                payment_status = 'pending'
                completed_at = None
            
            payment_methods = ['cash', 'card', 'online', 'esewa']
            payment = Payment.objects.create(
                subscription=subscription,
                amount=plan.price,
                payment_method=random.choice(payment_methods),
                status=payment_status,
                completed_at=completed_at,
                notes=f'Payment for {plan.name} subscription',
            )
            
            self.stdout.write(
                self.style.SUCCESS(
                    f'✓ Subscription & Payment: {member.user.full_name} - {plan.name} ({status})'
                )
            )
    
    def create_attendance_records(self, member_users):
        """Create attendance records for members with active subscriptions."""
        for member_user in member_users:
            member = member_user.member
            
            # Check if member has active subscription
            active_subscription = member.subscriptions.filter(status='active').first()
            if not active_subscription:
                continue
            
            # Create attendance records for last 14 days
            for days_ago in range(14, 0, -1):
                # Random attendance (70% chance of attending)
                if random.random() < 0.7:
                    check_in_date = date.today() - timedelta(days=days_ago)
                    check_in_time = timezone.now() - timedelta(
                        days=days_ago,
                        hours=random.randint(6, 20),
                        minutes=random.randint(0, 59)
                    )
                    
                    # 80% chance of checking out
                    if random.random() < 0.8:
                        check_out_time = check_in_time + timedelta(
                            hours=random.randint(1, 3),
                            minutes=random.randint(0, 59)
                        )
                    else:
                        check_out_time = None
                    
                    Attendance.objects.create(
                        member=member,
                        check_in=check_in_time,
                        check_out=check_out_time,
                        date=check_in_date,
                    )
            
            self.stdout.write(
                self.style.SUCCESS(
                    f'✓ Attendance records created for: {member.user.full_name}'
                )
            )
    
    def save_credentials_to_file(self, admin_users, staff_users, trainer_users, member_users):
        """Save all credentials to a markdown file."""
        from pathlib import Path
        
        credentials_file = Path(__file__).resolve().parent.parent.parent.parent.parent / 'CREDENTIALS.md'
        
        content = f"""# MScube Gym Management - Test User Credentials

**Generated on:** {date.today().strftime('%B %d, %Y')}

## Quick Access

All passwords follow the format: `RoleName@123`

## Admin Users ({len(admin_users)})

| Full Name | Email | Username | Password | Permissions |
|-----------|-------|----------|----------|-------------|
"""
        
        for admin in admin_users:
            profile = admin.adminprofile
            perms = []
            if profile.can_manage_users:
                perms.append('Users')
            if profile.can_manage_payments:
                perms.append('Payments')
            if profile.can_view_reports:
                perms.append('Reports')
            perms_str = ', '.join(perms) if perms else 'None'
            content += f"| {admin.full_name} | {admin.email} | {admin.username} | Admin@123 | {perms_str} |\n"
        
        content += f"\n## Staff Users ({len(staff_users)})\n\n"
        content += "| Full Name | Email | Username | Password | Department |\n"
        content += "|-----------|-------|----------|----------|------------|\n"
        
        for staff in staff_users:
            staff_profile = staff.staff
            content += f"| {staff.full_name} | {staff.email} | {staff.username} | Staff@123 | {staff_profile.department} |\n"
        
        content += f"\n## Trainers ({len(trainer_users)})\n\n"
        content += "| Full Name | Email | Username | Password | Specialization | Experience |\n"
        content += "|-----------|-------|----------|----------|----------------|------------|\n"
        
        for trainer in trainer_users:
            trainer_profile = trainer.trainer
            content += f"| {trainer.full_name} | {trainer.email} | {trainer.username} | Trainer@123 | {trainer_profile.specialization} | {trainer_profile.experience_years} yrs |\n"
        
        content += f"\n## Members ({len(member_users)})\n\n"
        content += "| Full Name | Email | Username | Password | Subscription Status |\n"
        content += "|-----------|-------|----------|----------|---------------------|\n"
        
        for member in member_users:
            member_profile = member.member
            sub = member_profile.subscriptions.first()
            status = sub.status if sub else 'None'
            content += f"| {member.full_name} | {member.email} | {member.username} | Member@123 | {status.capitalize()} |\n"
        
        content += "\n## Testing Notes\n\n"
        content += "- **Admin accounts** have varying permissions levels for testing\n"
        content += "- **Staff accounts** are assigned to different departments\n"
        content += "- **Trainers** have different specializations for testing trainer dashboards\n"
        content += "- **Members** have different subscription statuses (active, pending, expired) for testing\n\n"
        content += "## Usage\n\n"
        content += "```bash\n"
        content += "# Login to admin dashboard\n"
        content += "Email: admin@mscube.com\n"
        content += "Password: Admin@123\n\n"
        content += "# Login to staff dashboard\n"
        content += "Email: staff@mscube.com\n"
        content += "Password: Staff@123\n\n"
        content += "# Login to trainer dashboard\n"
        content += "Email: trainer1@mscube.com\n"
        content += "Password: Trainer@123\n\n"
        content += "# Login to member dashboard\n"
        content += "Email: member1@example.com\n"
        content += "Password: Member@123\n"
        content += "```\n\n"
        content += "---\n\n"
        content += "**Security Note:** This file contains test credentials only. Never commit real user credentials to version control.\n"
        
        with open(credentials_file, 'w') as f:
            f.write(content)
        
        self.stdout.write(self.style.SUCCESS(f'✓ Credentials saved to: {credentials_file}'))
    
    def print_summary(self, admin_users, staff_users, trainer_users, member_users):
        """Print summary of created test data."""
        self.stdout.write('\n' + self.style.SUCCESS('LOGIN CREDENTIALS:'))
        self.stdout.write(self.style.SUCCESS('-' * 60))
        
        self.stdout.write(self.style.WARNING(f'\nAdmins ({len(admin_users)}):'))
        for admin in admin_users:
            self.stdout.write(f'  Email: {admin.email}')
        self.stdout.write(f'  Password (all): Admin@123')
        
        self.stdout.write(self.style.WARNING(f'\nStaff ({len(staff_users)}):'))
        for staff in staff_users:
            self.stdout.write(f'  Email: {staff.email}')
        self.stdout.write(f'  Password (all): Staff@123')
        
        self.stdout.write(self.style.WARNING(f'\nTrainers ({len(trainer_users)}):'))
        for trainer in trainer_users:
            self.stdout.write(f'  Email: {trainer.email}')
        self.stdout.write(f'  Password (all): Trainer@123')
        
        self.stdout.write(self.style.WARNING(f'\nMembers ({len(member_users)}):'))
        for member in member_users:
            self.stdout.write(f'  Email: {member.email}')
        self.stdout.write(f'  Password (all): Member@123')
        
        self.stdout.write('\n' + self.style.SUCCESS('DATABASE SUMMARY:'))
        self.stdout.write(self.style.SUCCESS('-' * 60))
        self.stdout.write(f'Total Users: {User.objects.count()}')
        self.stdout.write(f'  - Admins: {AdminProfile.objects.count()}')
        self.stdout.write(f'  - Staff: {Staff.objects.count()}')
        self.stdout.write(f'  - Trainers: {Trainer.objects.count()}')
        self.stdout.write(f'  - Members: {Member.objects.count()}')
        self.stdout.write(f'\n** All credentials saved to CREDENTIALS.md **')
        self.stdout.write(f'\nMembership Plans: {MembershipPlan.objects.count()}')
        self.stdout.write(f'Subscriptions: {Subscription.objects.count()}')
        self.stdout.write(f'  - Active: {Subscription.objects.filter(status="active").count()}')
        self.stdout.write(f'  - Pending: {Subscription.objects.filter(status="pending").count()}')
        self.stdout.write(f'  - Expired: {Subscription.objects.filter(status="expired").count()}')
        self.stdout.write(f'Payments: {Payment.objects.count()}')
        self.stdout.write(f'Attendance Records: {Attendance.objects.count()}')
        
        self.stdout.write('\n' + self.style.SUCCESS('='*60))
        self.stdout.write(self.style.SUCCESS('You can now test the system with these users!'))
        self.stdout.write(self.style.SUCCESS('='*60) + '\n')
