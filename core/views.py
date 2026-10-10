from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login
from django.contrib.auth.decorators import login_required, user_passes_test
from django.db.models import Q, Sum
from django.utils import timezone
from django.db import models

from rest_framework import viewsets, status, permissions
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.decorators import api_view, permission_classes, action
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from django.shortcuts import get_object_or_404

import logging
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
logger = logging.getLogger(__name__)

from django.contrib.auth import get_user_model
User = get_user_model()

# সংশোধিত import - RolePermission রিমুভ করা হয়েছে
from .models import BusinessProfile, StaffRole, Staff, UserPermission
from .serializers import (
    BusinessProfileSerializer,
    UserSerializer,
    UserCreateSerializer,
    StaffRoleSerializer,
    StaffRoleCreateUpdateSerializer,
    StaffSerializer,
    StaffProfileSerializer,
    UserProfileSerializer,
    CustomTokenObtainPairSerializer,
    UserLoginSerializer,
    UserPermissionUpdateSerializer,
    UserPermissionResetSerializer,
    UserListSerializer,
    PermissionCheckSerializer,
    UserPermissionSerializer
)
from .utils import custom_response

# Import forms safely
try:
    from .forms import UserForm, UserCreationForm
except ImportError:
    UserForm = None
    UserCreationForm = None


# --------------------------
# JWT / Login Views
# --------------------------
class CustomTokenObtainPairView(TokenObtainPairView):
    serializer_class = CustomTokenObtainPairSerializer

class CustomLoginView(APIView):
    permission_classes = [AllowAny]

    def post(self, request, *args, **kwargs):
        serializer = UserLoginSerializer(data=request.data)

        if serializer.is_valid():
            user = serializer.validated_data['user']

            # JWT tokens
            token_serializer = CustomTokenObtainPairSerializer()
            refresh = token_serializer.get_token(user)

            # Permissions
            permissions = user.get_permissions()

            # একমাত্র ব্যবসার তথ্য
            business_data = BusinessProfileSerializer(
                BusinessProfile.get(), context={'request': request}
            ).data

            response_data = {
                "success": True,
                "message": "Login successful",
                "data": {
                    "user": {
                        "id": user.id,
                        "username": user.username,
                        "email": user.email,
                        "first_name": user.first_name,
                        "last_name": user.last_name,
                        "full_name": user.full_name,
                        "role": user.role,
                        "permission_source": user.permission_source,
                        "is_staff": user.is_staff,
                        "is_superuser": user.is_superuser,
                        "permissions": permissions,
                    },
                    "business": business_data,
                    "tokens": {
                        "refresh": str(refresh),
                        "access": str(refresh.access_token),
                    },
                },
            }

            return Response(response_data, status=status.HTTP_200_OK)

        return Response(
            {
                "success": False,
                "message": "Login failed",
                "errors": serializer.errors,
            },
            status=status.HTTP_401_UNAUTHORIZED,
        )


# --------------------------
# Base ViewSets
# --------------------------
class BaseViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        queryset = super().get_queryset()
        if not self.request.user.is_authenticated:
            return queryset.none()
        return queryset


# --------------------------
# Business Profile (একমাত্র ব্যবসা — নাম/লোগো/ফোন/ঠিকানা)
# --------------------------
class BusinessProfileView(APIView):
    """
    GET  /api/business/  — যেকোনো লগইন করা ইউজার
    PUT/PATCH /api/business/ — শুধু Admin/Super Admin (administration.edit)
    ক্লায়েন্ট এখানে যে নাম দেবে সেটাই সব জায়গায় দেখাবে।
    """
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def get(self, request):
        data = BusinessProfileSerializer(BusinessProfile.get(), context={'request': request}).data
        return custom_response(True, "Business profile", data, status.HTTP_200_OK)

    def _update(self, request, partial):
        user = request.user
        if not (user.role == User.Role.SUPER_ADMIN or user.is_superuser
                or user.has_permission('administration', 'edit')):
            return custom_response(False, "You don't have permission to change the business profile",
                                   None, status.HTTP_403_FORBIDDEN)
        profile = BusinessProfile.get()
        ser = BusinessProfileSerializer(profile, data=request.data, partial=partial,
                                        context={'request': request})
        if not ser.is_valid():
            return custom_response(False, "Please fix the highlighted fields.", ser.errors,
                                   status.HTTP_400_BAD_REQUEST)
        ser.save()
        return custom_response(True, "Business profile saved", ser.data, status.HTTP_200_OK)

    def put(self, request):
        return self._update(request, partial=False)

    def patch(self, request):
        return self._update(request, partial=True)


# -------------------------
# User ViewSet
# -------------------------
# -------------------------
# User ViewSet
# -------------------------
# -------------------------
# User ViewSet
# -------------------------
class UserViewSet(viewsets.ModelViewSet):
    serializer_class = UserSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        
        if not user.is_authenticated:
            return User.objects.none()
        
        queryset = User.objects.all()
        # Super Admin (মালিক) অন্য কারও তালিকায় দেখায় না, কেউ বদলাতেও পারে না
        if user.role != User.Role.SUPER_ADMIN:
            queryset = queryset.exclude(role=User.Role.SUPER_ADMIN)
        return queryset
        
    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return custom_response(
                success=True,
                message=f"Found {len(page)} users",
                data=serializer.data,
                status_code=status.HTTP_200_OK
            )
        
        serializer = self.get_serializer(queryset, many=True)
        return custom_response(
            success=True,
            message=f"Found {queryset.count()} users",
            data=serializer.data,
            status_code=status.HTTP_200_OK
        )
    # ───── লেখা (তৈরি / বদল / বন্ধ) — নিয়ম core/team.py তে ─────
    def create(self, request, *args, **kwargs):
        from . import team
        actor = request.user
        if not actor.has_permission('users', 'create'):
            return custom_response(False, "You don't have permission to add users", None, status.HTTP_403_FORBIDDEN)
        data, errors = team.validate_person(request.data, actor)
        if errors:
            return custom_response(False, "Please fix the highlighted fields.", errors, status.HTTP_400_BAD_REQUEST)
        password = data.pop('password')
        u = User(is_active=True, **data)
        u.set_password(password)
        u.save()   # role অনুযায়ী default permission এখানেই বসে
        return custom_response(True, f"{u.username} can now sign in.", team.person_row(u, actor), status.HTTP_201_CREATED)

    def update(self, request, *args, **kwargs):
        from . import team
        actor = request.user
        instance = self.get_object()
        if not actor.has_permission('users', 'edit') and actor.pk != instance.pk:
            return custom_response(False, "You don't have permission to edit users", None, status.HTTP_403_FORBIDDEN)
        if not team.can_touch(actor, instance):
            return custom_response(False, "You can't change this person.", None, status.HTTP_403_FORBIDDEN)
        # is_superuser, is_staff, permission_source এখান থেকে বদলায় না — শুধু নিচের ঘরগুলো
        allowed = {k: v for k, v in request.data.items()
                   if k in ('first_name', 'last_name', 'phone', 'username', 'email', 'role', 'password', 'is_active')}
        data, errors = team.validate_person(allowed, actor, instance=instance)
        if errors:
            return custom_response(False, "Please fix the highlighted fields.", errors, status.HTTP_400_BAD_REQUEST)
        problem = team.check_change(actor, instance, data)
        if problem:
            return custom_response(False, problem, None, status.HTTP_400_BAD_REQUEST)
        password = data.pop('password', None)
        role_changed = 'role' in data and data['role'] != instance.role
        for k, v in data.items():
            setattr(instance, k, v)
        if password:
            instance.set_password(password)
        instance.save()
        if role_changed:
            # নতুন role এর default permission — না হলে STAFF থেকে ADMIN করেও কিছু করতে পারত না
            instance.reset_to_role_permissions()
        instance.refresh_from_db()
        msg = "Saved."
        if 'is_active' in data:
            msg = f"{instance.username} can sign in again." if instance.is_active else f"{instance.username} can no longer sign in."
        elif role_changed:
            msg = f"{instance.username} is now {instance.get_role_display()}. Their access was reset to that role's defaults."
        return custom_response(True, msg, team.person_row(instance, actor), status.HTTP_200_OK)

    def destroy(self, request, *args, **kwargs):
        """মুছে ফেলার বদলে বন্ধ করি — তাদের করা বিক্রি/রসিদে "কে করেছে" থেকে যায়"""
        from . import team
        actor = request.user
        if not actor.has_permission('users', 'delete'):
            return custom_response(False, "You don't have permission to remove users", None, status.HTTP_403_FORBIDDEN)
        instance = self.get_object()
        if instance.id == actor.id:
            return custom_response(False, "You cannot remove your own account", None, status.HTTP_400_BAD_REQUEST)
        if not team.can_touch(actor, instance):
            return custom_response(False, "You can't change this person.", None, status.HTTP_403_FORBIDDEN)
        problem = team.check_change(actor, instance, {'is_active': False})
        if problem:
            return custom_response(False, problem, None, status.HTTP_400_BAD_REQUEST)
        instance.is_active = False
        instance.save(update_fields=['is_active'])
        return custom_response(True, f"{instance.username} was turned off. Their past work stays on record.", None, status.HTTP_200_OK)

    @action(detail=False, methods=['get'])
    def team(self, request):
        """web এর Staff page — প্রত্যেকের role, permission আর actor কী করতে পারবে"""
        from . import team as T
        actor = request.user
        if not actor.has_permission('users', 'view'):
            return custom_response(False, "You don't have permission to see users", None, status.HTTP_403_FORBIDDEN)
        qs = self.get_queryset().order_by('-is_active', 'first_name', 'username')
        rows = [T.person_row(u, actor) for u in qs]
        return custom_response(True, f"{len(rows)} people", {
            'results': rows,
            'limit': None,
            'active': sum(1 for r in rows if r['is_active']),
            'assignable': [r for r in T.ASSIGNABLE if T.can_assign(actor, r)],
            'can_manage_permissions': T.is_admin(actor),
        }, status.HTTP_200_OK)

    @action(detail=True, methods=['post'], url_path='set-password')
    def set_password(self, request, pk=None):
        from . import team
        actor = request.user
        target = self.get_object()
        if not (actor.has_permission('users', 'edit') and team.can_touch(actor, target)):
            return custom_response(False, "You can't change this person's password.", None, status.HTTP_403_FORBIDDEN)
        pw = request.data.get('password') or ''
        try:
            validate_password(pw, user=target)
        except DjangoValidationError as e:
            return custom_response(False, ' '.join(e.messages), {'password': ' '.join(e.messages)}, status.HTTP_400_BAD_REQUEST)
        target.set_password(pw)
        target.save(update_fields=['password'])
        return custom_response(True, f"Password changed for {target.username}.", None, status.HTTP_200_OK)

    @action(detail=True, methods=['post'])
    def assign_role(self, request, pk=None):
        user = self.get_object()
        request_user = request.user
        
        if not request_user.has_permission('users', 'edit'):
            return custom_response(
                False, 
                "You don't have permission to assign roles", 
                None, 
                status.HTTP_403_FORBIDDEN
            )
        
        role_id = request.data.get('role_id')
        if not role_id:
            return custom_response(
                False, 
                "Role ID is required", 
                None, 
                status.HTTP_400_BAD_REQUEST
            )
        
        try:
            role = StaffRole.objects.get(id=role_id)
            
            staff_profile, created = Staff.objects.get_or_create(user=user)
            
            staff_profile.role = role
            staff_profile.save()
            
            user.assign_role_permissions(role)
            
            return custom_response(
                True, 
                "Role assigned successfully", 
                UserSerializer(user).data, 
                status.HTTP_200_OK
            )
            
        except StaffRole.DoesNotExist:
            return custom_response(
                False, 
                "Role not found", 
                None, 
                status.HTTP_404_NOT_FOUND
            )
        except Exception as e:
            logger.error(f"Error assigning role: {str(e)}")
            return custom_response(
                False, 
                f"Error: {str(e)}", 
                None, 
                status.HTTP_500_INTERNAL_SERVER_ERROR
            )


# --------------------------
# User Permission Management Views
# --------------------------
class UserPermissionManagementView(APIView):
    """View for managing user permissions (Admin only)"""
    permission_classes = [IsAuthenticated]
    
    def post(self, request):
        """Update user permissions"""
        serializer = UserPermissionUpdateSerializer(
            data=request.data,
            context={'request': request}
        )
        
        if serializer.is_valid():
            user = serializer.save()
            return custom_response(
                True,
                "User permissions updated successfully",
                {
                    'user_id': user.id,
                    'username': user.username,
                    'permissions': user.get_permissions(),
                    'permission_source': user.permission_source
                },
                status.HTTP_200_OK
            )
        
        return custom_response(
            False,
            "Permission update failed",
            serializer.errors,
            status.HTTP_400_BAD_REQUEST
        )
    
    def delete(self, request):
        """Reset user permissions to role defaults"""
        serializer = UserPermissionResetSerializer(
            data=request.data,
            context={'request': request}
        )
        
        if serializer.is_valid():
            user = serializer.save()
            return custom_response(
                True,
                "User permissions reset to role defaults",
                {
                    'user_id': user.id,
                    'username': user.username,
                    'permissions': user.get_permissions(),
                    'permission_source': user.permission_source
                },
                status.HTTP_200_OK
            )
        
        return custom_response(
            False,
            "Permission reset failed",
            serializer.errors,
            status.HTTP_400_BAD_REQUEST
        )


class UserPermissionListView(APIView):
    """List all user permissions for a specific user"""
    permission_classes = [IsAuthenticated]
    
    def get(self, request, user_id):
        try:
            target_user = User.objects.get(id=user_id)
            request_user = request.user
            
            # Check permissions
            if not request_user.can_manage_user(target_user):
                return custom_response(
                    False,
                    "You don't have permission to view this user's permissions",
                    None,
                    status.HTTP_403_FORBIDDEN
                )
            
            # Get all permissions
            permissions = target_user.get_permissions()
            custom_perms = UserPermission.objects.filter(user=target_user, is_active=True)

            # App এ Save/Reset বাটন চালু থাকবে কিনা — update serializer এর নিয়মের সাথে মিল রেখে
            editable = target_user.role != User.Role.SUPER_ADMIN and not (
                request_user.role == User.Role.ADMIN
                and target_user.role == User.Role.ADMIN
                and target_user != request_user
            )
            
            return custom_response(
                True,
                "User permissions fetched successfully",
                {
                    'user': {
                        'id': target_user.id,
                        'username': target_user.username,
                        'full_name': target_user.full_name,
                        'email': target_user.email,
                        'role': target_user.role,
                        'role_display': target_user.get_role_display(),
                        'is_active': target_user.is_active,
                        'permission_source': target_user.permission_source,
                        'editable': editable,
                    },
                    'permissions': permissions,
                    'custom_permissions': UserPermissionSerializer(custom_perms, many=True).data
                },
                status.HTTP_200_OK
            )
            
        except User.DoesNotExist:
            return custom_response(
                False,
                "User not found",
                None,
                status.HTTP_404_NOT_FOUND
            )
        except Exception as e:
            logger.error(f"Error fetching user permissions: {str(e)}")
            return custom_response(
                False,
                "Error fetching user permissions",
                None,
                status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class BusinessUsersView(APIView):
    """সব ইউজারের তালিকা (admin dashboard এর জন্য)"""
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        user = request.user
        
        if user.role == User.Role.SUPER_ADMIN:
            users = User.objects.all()
        elif user.role == User.Role.ADMIN:
            users = User.objects.exclude(role=User.Role.SUPER_ADMIN)
        else:
            return custom_response(
                False,
                "You don't have permission to view users",
                None,
                status.HTTP_403_FORBIDDEN
            )
        
        serializer = UserListSerializer(users, many=True)
        
        return custom_response(
            True,
            "Users fetched successfully",
            {
                'total_users': users.count(),
                'users': serializer.data
            },
            status.HTTP_200_OK
        )


class PermissionCheckView(APIView):
    """Check if user has specific permission"""
    permission_classes = [IsAuthenticated]
    
    def post(self, request):
        serializer = PermissionCheckSerializer(data=request.data)
        
        if serializer.is_valid():
            module = serializer.validated_data['module']
            action = serializer.validated_data.get('action')
            
            has_perm = request.user.has_permission(module, action)
            
            return custom_response(
                True,
                "Permission check completed",
                {
                    'has_permission': has_perm,
                    'module': module,
                    'action': action
                },
                status.HTTP_200_OK
            )
        
        return custom_response(
            False,
            "Invalid request data",
            serializer.errors,
            status.HTTP_400_BAD_REQUEST
        )


# --------------------------
# Staff Role ViewSet
# --------------------------
class StaffRoleViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        return StaffRole.objects.all()

    def get_serializer_class(self):
        if self.action in ['create', 'update', 'partial_update']:
            return StaffRoleCreateUpdateSerializer
        return StaffRoleSerializer

    def create(self, request, *args, **kwargs):
        if not request.user.has_permission('administration', 'create'):
            return custom_response(
                False, 
                "You don't have permission to create roles", 
                None, 
                status.HTTP_403_FORBIDDEN
            )
        
        return super().create(request, *args, **kwargs)

    def update(self, request, *args, **kwargs):
        if not request.user.has_permission('administration', 'edit'):
            return custom_response(
                False, 
                "You don't have permission to edit roles", 
                None, 
                status.HTTP_403_FORBIDDEN
            )
        
        return super().update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        if not request.user.has_permission('administration', 'delete'):
            return custom_response(
                False, 
                "You don't have permission to delete roles", 
                None, 
                status.HTTP_403_FORBIDDEN
            )
        
        return super().destroy(request, *args, **kwargs)


# --------------------------
# Staff ViewSet
# --------------------------
class StaffViewSet(BaseViewSet):
    queryset = Staff.objects.all()
    serializer_class = StaffSerializer
    
    def get_queryset(self):
        return Staff.objects.all()

    def create(self, request, *args, **kwargs):
        if not request.user.has_permission('administration', 'create'):
            return custom_response(
                False, 
                "You don't have permission to create staff", 
                None, 
                status.HTTP_403_FORBIDDEN
            )
        
        return super().create(request, *args, **kwargs)


# --------------------------
# Change Password
# --------------------------
class ChangePasswordAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        try:
            user = request.user
            current_password = request.data.get('current_password')
            new_password = request.data.get('new_password')
            confirm_password = request.data.get('confirm_password')

            if not current_password or not new_password or not confirm_password:
                return custom_response(
                    False, 
                    "All fields are required", 
                    None, 
                    status.HTTP_400_BAD_REQUEST
                )

            if new_password != confirm_password:
                return custom_response(
                    False, 
                    "New passwords do not match", 
                    None, 
                    status.HTTP_400_BAD_REQUEST
                )

            if not user.check_password(current_password):
                return custom_response(
                    False, 
                    "Current password is incorrect", 
                    None, 
                    status.HTTP_400_BAD_REQUEST
                )

            if len(new_password) < 8:
                return custom_response(
                    False, 
                    "New password must be at least 8 characters long", 
                    None, 
                    status.HTTP_400_BAD_REQUEST
                )

            user.set_password(new_password)
            user.save()
            logger.info(f"Password changed for user: {user.username}")

            return custom_response(True, "Password changed successfully", None, status.HTTP_200_OK)
        except Exception as e:
            logger.error(f"Password change failed: {str(e)}", exc_info=True)
            return custom_response(
                False, 
                "Password change failed", 
                None, 
                status.HTTP_500_INTERNAL_SERVER_ERROR
            )


# --------------------------
# Profile API
# --------------------------
class ProfileAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        try:
            user = request.user
            has_staff_profile = hasattr(user, 'staff_profile') and user.staff_profile

            profile_data = {
                'user': UserProfileSerializer(user).data,
                'staff_profile': StaffProfileSerializer(user.staff_profile).data if has_staff_profile else None,
                'permissions': user.get_permissions(),
                'permission_source': user.permission_source,
                'business_info': BusinessProfileSerializer(BusinessProfile.get(), context={'request': request}).data
            }

            logger.info(f"User profile fetched for: {user.username}")
            return custom_response(
                True, 
                "User profile fetched successfully", 
                profile_data, 
                status.HTTP_200_OK
            )

        except Exception as e:
            logger.error(f"Error fetching user profile: {str(e)}", exc_info=True)
            return custom_response(
                False, 
                "Error fetching user profile", 
                None, 
                status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    def patch(self, request):
        try:
            user = request.user
            data = request.data.copy()
            
            # Remove sensitive fields
            sensitive_fields = ['password', 'is_superuser', 'is_staff', 'role', 'username']
            for field in sensitive_fields:
                data.pop(field, None)

            serializer = UserProfileSerializer(user, data=data, partial=True, context={'request': request})
            if serializer.is_valid():
                serializer.save()
                
                has_staff_profile = hasattr(user, 'staff_profile') and user.staff_profile
                updated_profile_data = {
                    'user': UserProfileSerializer(user).data,
                    'staff_profile': StaffProfileSerializer(user.staff_profile).data if has_staff_profile else None,
                    'permissions': user.get_permissions(),
                    'permission_source': user.permission_source,
                    'business_info': BusinessProfileSerializer(BusinessProfile.get(), context={'request': request}).data
                }
                
                return custom_response(
                    True, 
                    "Profile updated successfully", 
                    updated_profile_data, 
                    status.HTTP_200_OK
                )
            else:
                return custom_response(
                    False, 
                    "Validation error", 
                    serializer.errors, 
                    status.HTTP_400_BAD_REQUEST
                )
        except Exception as e:
            logger.error(f"Error updating user profile: {str(e)}", exc_info=True)
            return custom_response(
                False, 
                "Error updating profile", 
                None, 
                status.HTTP_500_INTERNAL_SERVER_ERROR
            )


# --------------------------
# User Permissions
# --------------------------

class UserPermissionsAPIView(APIView):
    """
    Get user permissions and check specific permissions
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        """
        Get complete user permissions
        """
        try:
            user = request.user
            business = BusinessProfile.get()

            permissions = user.get_permissions()
            can_manage_users = self._can_manage_users(user)
            data_access_scope = self._get_data_access_scope(user)

            permissions_data = {
                'user': {
                    'id': user.id,
                    'username': user.username,
                    'email': user.email,
                    'first_name': user.first_name,
                    'last_name': user.last_name,
                    'role': user.role,
                    'role_display': user.get_role_display(),
                    'is_superuser': user.is_superuser,
                    'is_staff': user.is_staff,
                    'is_active': user.is_active,
                    'is_verified': user.is_verified,
                },
                'business': {'name': business.name},
                'permissions': permissions,
                'capabilities': {
                    'can_manage_users': can_manage_users,
                    'can_manage_business': user.role in [user.Role.SUPER_ADMIN, user.Role.ADMIN],
                    'can_access_dashboard': user.can_access_dashboard,
                    'can_export_reports': user.reports_export,
                    'data_access_scope': data_access_scope,
                },
                'system': {
                    'permission_source': user.permission_source,
                }
            }

            return custom_response(
                success=True,
                message="User permissions fetched successfully",
                data=permissions_data,
                status_code=status.HTTP_200_OK
            )

        except Exception as e:
            logger.error(f"Error fetching user permissions: {str(e)}", exc_info=True)
            return custom_response(
                success=False,
                message="Error fetching permissions",
                data=None,
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    def post(self, request):
        """
        Check specific permission
        """
        try:
            module = request.data.get('module')
            action = request.data.get('action')

            if not module:
                return custom_response(
                    success=False,
                    message="Module is required",
                    data=None,
                    status_code=status.HTTP_400_BAD_REQUEST
                )

            user = request.user
            has_perm = user.has_permission(module, action)

            # Viewer শুধু দেখতে/এক্সপোর্ট করতে পারে
            if has_perm and self._is_data_module(module):
                if user.role == user.Role.VIEWER and action not in ['view', 'export']:
                    has_perm = False

            return custom_response(
                success=True,
                message="Permission check completed",
                data={
                    'has_permission': has_perm,
                    'module': module,
                    'action': action or 'view',
                    'role': user.role,
                    'permission_source': user.permission_source,
                    'validation': {
                        'role_check_passed': True,
                        'permission_check_passed': has_perm
                    }
                },
                status_code=status.HTTP_200_OK
            )

        except Exception as e:
            logger.error(f"Error checking permission: {str(e)}", exc_info=True)
            return custom_response(
                success=False,
                message="Error checking permission",
                data=None,
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    def _can_manage_users(self, user):
        """
        Check if user can manage other users
        """
        if user.role in (user.Role.SUPER_ADMIN, user.Role.ADMIN):
            return True
        return user.users_create or user.users_edit or user.users_delete

    def _get_data_access_scope(self, user):
        """
        Determine user's data access scope based on role and permissions
        """
        scope_mapping = {
            user.Role.SUPER_ADMIN: {
                'scope': 'all',
                'description': 'Can access all data',
                'can_manage_all': True
            },
            user.Role.ADMIN: {
                'scope': 'all',
                'description': 'Can access all data',
                'can_manage_all': True
            },
            user.Role.MANAGER: {
                'scope': 'restricted',
                'description': 'Can access most data',
                'can_manage_all': False
            },
            user.Role.STAFF: {
                'scope': 'limited',
                'description': 'Limited access',
                'can_manage_all': False
            },
            user.Role.VIEWER: {
                'scope': 'view_only',
                'description': 'View-only access',
                'can_manage_all': False
            }
        }

        scope = dict(scope_mapping.get(user.role, {
            'scope': 'unknown',
            'description': 'Unknown role',
            'can_manage_all': False
        }))

        if not user.can_access_dashboard:
            scope['dashboard_access'] = False
            scope['description'] += ' (No dashboard access)'

        return scope

    def _is_data_module(self, module):
        """
        Check if module contains business data
        """
        data_modules = [
            'sales', 'money_receipt', 'purchases', 'products',
            'accounts', 'customers', 'suppliers', 'expense',
            'return', 'reports'
        ]
        return module in data_modules



# --------------------------
# Image update endpoints
# --------------------------
class BusinessLogoUpdateAPIView(APIView):
    """PATCH /api/business/logo/  (multipart, field: logo)"""
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]

    def patch(self, request, *args, **kwargs):
        try:
            if request.user.role != User.Role.SUPER_ADMIN and not request.user.has_permission('administration', 'edit'):
                return custom_response(False, "You don't have permission to change the logo", None, status.HTTP_403_FORBIDDEN)

            file = request.FILES.get('logo')
            if not file:
                return custom_response(False, "No 'logo' file provided", None, status.HTTP_400_BAD_REQUEST)

            if file.size > 5 * 1024 * 1024:
                return custom_response(False, "File size should not exceed 5MB", None, status.HTTP_400_BAD_REQUEST)

            content_type = getattr(file, 'content_type', '') or ''
            if not content_type.startswith('image/'):
                return custom_response(False, "Uploaded file is not an image", None, status.HTTP_400_BAD_REQUEST)

            business = BusinessProfile.get()
            business.logo = file
            business.save()

            serializer = BusinessProfileSerializer(business, context={'request': request})
            return custom_response(True, "Logo updated successfully", serializer.data, status.HTTP_200_OK)
        except Exception as e:
            logger.exception("Business logo update failed")
            return custom_response(False, f"Logo update failed: {str(e)}", None, status.HTTP_500_INTERNAL_SERVER_ERROR)


class ResetPermissionsAPIView(APIView):
    permission_classes = [IsAuthenticated]
    
    def post(self, request):
        """
        Reset user permissions to role defaults
        Expected JSON: {"user_id": 123}
        """
        user_id = request.data.get('user_id')
        
        if not user_id:
            return Response({
                'status': False,
                'message': 'user_id is required'
            }, status=400)
        
        try:
            user = User.objects.get(id=user_id)
        except User.DoesNotExist:
            return Response({
                'status': False,
                'message': 'User not found'
            }, status=404)
        
        # SECURITY: শুধু Super Admin / Admin রিসেট করতে পারে (Admin কখনো Super Admin কে নয়)।
        if request.user.role not in [User.Role.SUPER_ADMIN, User.Role.ADMIN] or not request.user.can_manage_user(user):
            return Response({
                'status': False,
                'message': 'You do not have permission to reset user permissions'
            }, status=403)
        
        # Reset user permissions to role defaults
        user.reset_to_role_permissions()
        
        return Response({
            'status': True,
            'message': 'Permissions reset to role defaults successfully',
            'data': {
                'user': {
                    'id': user.id,
                    'username': user.username,
                    'role': user.role,
                    'permission_source': user.permission_source,
                }
            }
        })



class UserProfileImageUpdateAPIView(APIView):
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]

    def patch(self, request, pk=None, *args, **kwargs):
        try:
            if pk is not None:
                if request.user.role != User.Role.SUPER_ADMIN:
                    return custom_response(
                        False, 
                        "Not authorized to update other users' profile pictures", 
                        None, 
                        status.HTTP_403_FORBIDDEN
                    )
                target_user = get_object_or_404(User, pk=pk)
            else:
                target_user = request.user

            file = request.FILES.get('profile_picture')
            if not file:
                return custom_response(
                    False, 
                    "No 'profile_picture' file provided", 
                    None, 
                    status.HTTP_400_BAD_REQUEST
                )

            if file.size > 2 * 1024 * 1024:
                return custom_response(
                    False, 
                    "File size should not exceed 2MB", 
                    None, 
                    status.HTTP_400_BAD_REQUEST
                )

            content_type = getattr(file, 'content_type', '') or ''
            if not content_type.startswith('image/'):
                return custom_response(
                    False, 
                    "Uploaded file is not an image", 
                    None, 
                    status.HTTP_400_BAD_REQUEST
                )

            target_user.profile_picture = file
            target_user.save()

            serializer = UserProfileSerializer(target_user, context={'request': request})
            return custom_response(
                True, 
                "Profile picture updated successfully", 
                serializer.data, 
                status.HTTP_200_OK
            )
        except Exception as e:
            logger.exception("Profile picture update failed")
            return custom_response(
                False, 
                f"Profile picture update failed: {str(e)}", 
                None, 
                status.HTTP_500_INTERNAL_SERVER_ERROR
            )


# --------------------------
# Dashboard Stats
# --------------------------
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def user_dashboard_stats(request):
    try:
        try:
            from sales.models import Sale
            from purchases.models import Purchase
            from products.models import Product
            from customers.models import Customer
            from suppliers.models import Supplier
            
            stats = {
                'today_sales': Sale.objects.filter(sale_date__date=timezone.now().date()).aggregate(total=Sum('grand_total'))['total'] or 0,
                'today_orders': Sale.objects.filter(sale_date__date=timezone.now().date()).count(),
                'total_products': Product.objects.filter(is_active=True).count(),
                'total_customers': Customer.objects.filter(is_active=True).count(),
                'total_suppliers': Supplier.objects.filter(is_active=True).count(),
                'pending_purchases': Purchase.objects.filter(status='pending').count(),
                'due_sales': Sale.objects.filter(due_amount__gt=0).aggregate(total_due=Sum('due_amount'))['total_due'] or 0,
            }
            
            for key, value in stats.items():
                if hasattr(value, '__float__'):
                    stats[key] = float(value)
                    
        except ImportError:
            stats = {
                'today_sales': 0,
                'today_orders': 0,
                'total_products': 0,
                'total_customers': 0,
                'total_suppliers': 0,
                'pending_purchases': 0,
                'due_sales': 0,
            }

        return custom_response(
            True, 
            "Dashboard stats fetched successfully", 
            stats, 
            status.HTTP_200_OK
        )

    except Exception as e:
        logger.error(f"Error fetching dashboard stats: {str(e)}", exc_info=True)
        return custom_response(
            False, 
            "Error fetching dashboard statistics", 
            None, 
            status.HTTP_500_INTERNAL_SERVER_ERROR
        )


# --------------------------
# Admin Web Views (Optional)
# --------------------------
def admin_signup(request):
    # বন্ধ: নিজে নিজে নতুন অ্যাকাউন্ট খোলা যায় না। ইউজার শুধু অ্যাডমিন যোগ করে (/app/ → Staff)।
    return redirect('/app/login/')


def admin_login(request):
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        user = authenticate(request, username=username, password=password)
        
        if user is not None:
            if user.is_active:
                if user.is_staff or user.role in [User.Role.ADMIN, User.Role.SUPER_ADMIN]:
                    login(request, user)
                    return redirect('admin_dashboard')
                else:
                    return render(request, 'admin_login.html', {'error': 'This account does not have admin privileges.'})
            else:
                return render(request, 'admin_login.html', {'error': 'Account is inactive.'})
        else:
            return render(request, 'admin_login.html', {'error': 'Invalid username or password.'})
    
    return render(request, 'admin_login.html')


@login_required
@user_passes_test(lambda u: u.role == User.Role.ADMIN)
def dashboard(request):
    return render(request, 'admin_dashboard.html')


@login_required
@user_passes_test(lambda u: u.role == User.Role.ADMIN)
def user_list(request):
    users = User.objects.exclude(id=request.user.id).exclude(role=User.Role.SUPER_ADMIN)
    return render(request, 'user_list.html', {'users': users})


@login_required
@user_passes_test(lambda u: u.role == User.Role.ADMIN)
def create_user(request):
    if UserForm is None:
        return render(request, 'error.html', {'error': 'Forms module not available'})
    
    if request.method == 'POST':
        form = UserForm(request.POST)
        if form.is_valid():
            user = form.save(commit=False)
            user.is_staff = user.role in [User.Role.ADMIN, User.Role.MANAGER]
            user.save()
            return redirect('user_list')
    else:
        form = UserForm()
    
    return render(request, 'create_user.html', {'form': form})


def user_management(request):
    if UserCreationForm is None:
        return render(request, 'error.html', {'error': 'Forms module not available'})
    
    users = User.objects.all()
    form = UserCreationForm()
    
    if request.method == "POST":
        form = UserCreationForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect('user_management')
    
    return render(request, "user_management.html", {"users": users, "form": form})


def home(request):
    return render(request, "home.html")