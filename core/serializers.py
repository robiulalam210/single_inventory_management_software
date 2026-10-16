from rest_framework import serializers
from .models import BusinessProfile, User, StaffRole, Staff, UserPermission
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from django.contrib.auth import authenticate
from rest_framework_simplejwt.tokens import RefreshToken


# -----------------------------
# Custom Token Serializer
# -----------------------------
class CustomTokenObtainPairSerializer(TokenObtainPairSerializer):
    def validate(self, attrs):
        data = super().validate(attrs)
        user = self.user
        
        # Get user permissions
        permissions = user.get_permissions()
        
        # Extra data returned in login response
        data["user"] = {
            "id": user.id,
            "username": user.username,
            "email": user.email,
            "first_name": user.first_name,
            "last_name": user.last_name,
            "role": user.role,
            "permission_source": user.permission_source,
            "is_staff": user.is_staff,
            "is_superuser": user.is_superuser,
            "business_name": BusinessProfile.get().name,
            "permissions": permissions
        }
        
        return data

    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)
        
        # Custom claims
        token["username"] = user.username
        token["role"] = user.role
        token["user_id"] = user.id
        token["permission_source"] = user.permission_source

        return token


# -----------------------------
# Business Profile Serializer (একমাত্র ব্যবসা)
# -----------------------------
class BusinessProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = BusinessProfile
        fields = [
            'id', 'name', 'tagline', 'phone', 'whatsapp', 'email', 'address',
            'website', 'trade_license', 'logo', 'currency', 'updated_at'
        ]
        read_only_fields = ['id', 'updated_at']

    def validate_name(self, value):
        value = (value or '').strip()
        if not value:
            raise serializers.ValidationError('Enter the business name.')
        return value


# -----------------------------
# User Permission Serializers
# -----------------------------
class UserPermissionSerializer(serializers.ModelSerializer):
    module_display = serializers.CharField(source='get_module_display', read_only=True)
    
    class Meta:
        model = UserPermission
        fields = [
            'id', 'module', 'module_display', 'can_view', 'can_create', 'can_edit',
            'can_delete', 'can_create_pos', 'can_create_short', 'can_export',
            'is_active', 'created_at', 'updated_at'
        ]
        read_only_fields = ['created_at', 'updated_at']


# -----------------------------
# User Serializers
# -----------------------------
class UserProfileSerializer(serializers.ModelSerializer):
    business_info = serializers.SerializerMethodField()
    full_name = serializers.SerializerMethodField()
    permissions = serializers.SerializerMethodField()
    custom_permissions = UserPermissionSerializer(many=True, read_only=True)
    
    class Meta:
        model = User
        fields = [
            'id', 'username', 'email', 'first_name', 'last_name', 'full_name',
            'role', 'permission_source', 'business_info', 'phone', 
            'profile_picture', 'date_of_birth', 'is_verified', 'last_login', 
            'date_joined', 'permissions', 'custom_permissions', 'is_active', 
            'is_staff', 'is_superuser'
        ]
        read_only_fields = [
            'id', 'is_verified', 'last_login', 'date_joined', 
            'permissions', 'custom_permissions', 'permission_source',
            'is_active', 'is_staff', 'is_superuser'
        ]

    def get_full_name(self, obj):
        return f"{obj.first_name} {obj.last_name}".strip()

    def get_permissions(self, obj):
        return obj.get_permissions()

    def get_business_info(self, obj):
        return BusinessProfileSerializer(BusinessProfile.get(), context=self.context).data


class UserSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, required=False)
    full_name = serializers.SerializerMethodField()
    permissions = serializers.SerializerMethodField()
    permission_source = serializers.CharField(read_only=True)
    custom_permissions = UserPermissionSerializer(many=True, read_only=True)
    
    class Meta:
        model = User
        fields = [
            "id", "username", "email", "password", "first_name", "last_name", 
            "full_name", "role", "permission_source", 
            "phone", "is_active", "is_staff", "is_superuser", "is_verified", 
            "permissions", "custom_permissions", "date_joined", "last_login"
        ]
        extra_kwargs = {
            'password': {'write_only': True, 'required': False},
            'role': {'required': True}
        }

    def get_full_name(self, obj):
        return f"{obj.first_name} {obj.last_name}".strip()

    def get_permissions(self, obj):
        return obj.get_permissions()

    def create(self, validated_data):
        password = validated_data.pop('password', None)
        
        # Set default role if not provided
        if 'role' not in validated_data:
            validated_data['role'] = User.Role.STAFF
        
        user = User.objects.create(**validated_data)
        
        if password:
            user.set_password(password)
        else:
            # Set default password
            user.set_password('password123')
        
        user.save()
        return user

    def update(self, instance, validated_data):
        password = validated_data.pop('password', None)
        
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        
        if password:
            instance.set_password(password)
        
        instance.save()
        return instance


class UserCreateSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, required=True)
    
    class Meta:
        model = User
        fields = [
            "id", "username", "email", "password", "first_name", "last_name",
            "role", "phone", "is_active"
        ]
        extra_kwargs = {
            'password': {'write_only': True},
            'role': {'required': True}
        }

    def create(self, validated_data):
        user = User.objects.create_user(**validated_data)
        return user


# -----------------------------
# User Permission Management Serializers
# -----------------------------
class PermissionActionSerializer(serializers.Serializer):
    """Serializer for individual permission actions"""
    view = serializers.BooleanField(default=False)
    create = serializers.BooleanField(default=False)
    edit = serializers.BooleanField(default=False)
    delete = serializers.BooleanField(default=False)
    create_pos = serializers.BooleanField(default=False)
    create_short = serializers.BooleanField(default=False)
    export = serializers.BooleanField(default=False)


class UserPermissionUpdateSerializer(serializers.Serializer):
    """Serializer for updating user permissions by admin"""
    user_id = serializers.IntegerField(required=True)
    permissions = serializers.DictField(
        child=PermissionActionSerializer(),
        required=True
    )
    
    def validate(self, attrs):
        user_id = attrs.get('user_id')
        permissions = attrs.get('permissions')
        
        try:
            user = User.objects.get(id=user_id)
        except User.DoesNotExist:
            raise serializers.ValidationError({"user_id": "User not found"})
        
        # Check if requesting user is admin/super admin
        request_user = self.context['request'].user
        
        if request_user.role not in [User.Role.SUPER_ADMIN, User.Role.ADMIN]:
            raise serializers.ValidationError(
                "Only admins can update user permissions"
            )
        
        if request_user.role == User.Role.ADMIN:
            # Admin cannot manage other admins
            if user.role == User.Role.ADMIN and user != request_user:
                raise serializers.ValidationError(
                    "Admin cannot update other admin permissions"
                )
        
        # Super Admin সবসময় full access পায় (model.save() এ জোর করে সব True হয়)
        if user.role == User.Role.SUPER_ADMIN:
            raise serializers.ValidationError(
                "Super Admin always has full access; permissions cannot be changed"
            )
        
        # Validate module names
        valid_modules = [
            'dashboard', 'sales', 'money_receipt', 'purchases', 'products',
            'accounts', 'customers', 'suppliers', 'expense', 'return',
            'reports', 'users', 'administration', 'settings'
        ]
        
        for module in permissions.keys():
            if module not in valid_modules:
                raise serializers.ValidationError(
                    f"Invalid module: {module}. Valid modules are: {', '.join(valid_modules)}"
                )
        
        return attrs
    
    def save(self):
        user_id = self.validated_data['user_id']
        permissions = self.validated_data['permissions']
        request_user = self.context['request'].user
        
        user = User.objects.get(id=user_id)
        
        # Update user permissions
        user.update_custom_permissions(permissions)
        
        # Create UserPermission records for tracking
        for module, perms in permissions.items():
            UserPermission.objects.update_or_create(
                user=user,
                module=module,
                defaults={
                    'can_view': perms.get('view', False),
                    'can_create': perms.get('create', False),
                    'can_edit': perms.get('edit', False),
                    'can_delete': perms.get('delete', False),
                    'can_create_pos': perms.get('create_pos', False),
                    'can_create_short': perms.get('create_short', False),
                    'can_export': perms.get('export', False),
                    'created_by': request_user,
                    'is_active': True
                }
            )
        
        return user


class UserPermissionResetSerializer(serializers.Serializer):
    """Serializer for resetting user permissions to role defaults"""
    user_id = serializers.IntegerField(required=True)
    
    def validate(self, attrs):
        user_id = attrs.get('user_id')
        
        try:
            user = User.objects.get(id=user_id)
        except User.DoesNotExist:
            raise serializers.ValidationError({"user_id": "User not found"})
        
        # Check if requesting user is admin/super admin
        request_user = self.context['request'].user
        
        if request_user.role not in [User.Role.SUPER_ADMIN, User.Role.ADMIN]:
            raise serializers.ValidationError(
                "Only admins can reset user permissions"
            )
        
        if request_user.role == User.Role.ADMIN:
            if user.role == User.Role.SUPER_ADMIN:
                raise serializers.ValidationError(
                    "You cannot reset a Super Admin's permissions"
                )
        
        return attrs
    
    def save(self):
        user_id = self.validated_data['user_id']
        user = User.objects.get(id=user_id)
        
        # Reset to role permissions
        user.reset_to_role_permissions()
        
        # Deactivate all custom permissions
        UserPermission.objects.filter(user=user).update(is_active=False)
        
        return user


class UserListSerializer(serializers.ModelSerializer):
    """Serializer for listing users with basic info (for admin view)"""
    full_name = serializers.SerializerMethodField()
    permission_source = serializers.CharField(read_only=True)
    
    class Meta:
        model = User
        fields = [
            'id', 'username', 'email', 'full_name', 'role', 'permission_source',
            'phone', 'is_active', 'date_joined',
            'last_login'
        ]
    
    def get_full_name(self, obj):
        return f"{obj.first_name} {obj.last_name}".strip()


# -----------------------------
# Staff Role Serializers
# -----------------------------
class StaffRoleSerializer(serializers.ModelSerializer):
    permissions = serializers.SerializerMethodField()
    
    class Meta:
        model = StaffRole
        fields = [
            'id', 'name', 'role_type', 'description',
            'default_permissions', 'permissions',
            'is_active', 'created_at', 'updated_at'
        ]
        read_only_fields = ['created_at', 'updated_at']

    def get_permissions(self, obj):
        return obj.get_permissions_dict()


class StaffRoleCreateUpdateSerializer(serializers.ModelSerializer):
    permissions = serializers.JSONField(write_only=True, required=False)
    
    class Meta:
        model = StaffRole
        fields = [
            'id', 'name', 'role_type', 'description',
            'permissions', 'is_active'
        ]

    def create(self, validated_data):
        permissions_data = validated_data.pop('permissions', None)
        instance = super().create(validated_data)
        
        if permissions_data:
            instance.update_permissions(permissions_data)
        
        return instance

    def update(self, instance, validated_data):
        permissions_data = validated_data.pop('permissions', None)
        instance = super().update(instance, validated_data)
        
        if permissions_data is not None:
            instance.update_permissions(permissions_data)
        
        return instance


# -----------------------------
# Staff Serializers
# -----------------------------
class StaffProfileSerializer(serializers.ModelSerializer):
    user_info = serializers.SerializerMethodField()
    role_info = StaffRoleSerializer(source='role', read_only=True)
    is_currently_active = serializers.BooleanField(read_only=True)
    employment_duration = serializers.IntegerField(read_only=True)
    total_compensation = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    
    class Meta:
        model = Staff
        fields = [
            'id', 'user', 'user_info', 'role', 'role_info',
            'phone', 'alternate_phone', 'image', 'designation',
            'employment_type', 'employee_id', 'department',
            'salary', 'commission', 'bonus', 'total_compensation',
            'is_main_user', 'status', 'joining_date', 'leaving_date', 'contract_end_date',
            'address', 'emergency_contact', 'emergency_phone',
            'is_currently_active', 'employment_duration', 'created_at', 'updated_at'
        ]
        read_only_fields = [
            'id', 'employee_id', 'is_currently_active', 
            'employment_duration', 'total_compensation', 'created_at', 'updated_at'
        ]

    def get_user_info(self, obj):
        if obj.user:
            return {
                "id": obj.user.id,
                "username": obj.user.username,
                "email": obj.user.email,
                "first_name": obj.user.first_name,
                "last_name": obj.user.last_name,
                "role": obj.user.role,
                "permission_source": obj.user.permission_source,
                "full_name": obj.user.full_name,
            }
        return None


class StaffSerializer(serializers.ModelSerializer):
    user_info = serializers.SerializerMethodField()
    role_name = serializers.CharField(source='role.name', read_only=True)
    role_type = serializers.CharField(source='role.role_type', read_only=True)
    is_currently_active = serializers.BooleanField(read_only=True)
    total_compensation = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    
    class Meta:
        model = Staff
        fields = [
            "id", "user", "user_info", "role", "role_name", "role_type",
            "phone", "designation", "employment_type", "employee_id", "department",
            "salary", "commission", "bonus", "total_compensation",
            "is_main_user", "status", "joining_date", "employment_duration",
            "is_currently_active", "created_at", "updated_at"
        ]

    def get_user_info(self, obj):
        if obj.user:
            return {
                "id": obj.user.id,
                "username": obj.user.username,
                "email": obj.user.email,
                "first_name": obj.user.first_name,
                "last_name": obj.user.last_name,
                "role": obj.user.role,
                "permission_source": obj.user.permission_source,
                "full_name": obj.user.full_name,
                "is_active": obj.user.is_active,
            }
        return None


# -----------------------------
# Login Serializer
# -----------------------------
class UserLoginSerializer(serializers.Serializer):
    username = serializers.CharField(required=False)
    email = serializers.EmailField(required=False)
    password = serializers.CharField()

    def validate(self, attrs):
        username = attrs.get('username')
        email = attrs.get('email')
        password = attrs.get('password')

        if not (username or email):
            raise serializers.ValidationError('Must include "username" or "email"')
        
        if not password:
            raise serializers.ValidationError('Must include "password"')

        # Authenticate user
        if email:
            try:
                user_obj = User.objects.get(email=email)
                username = user_obj.username
            except User.DoesNotExist:
                raise serializers.ValidationError('Invalid credentials')
        
        user = authenticate(username=username, password=password)
        
        if not user:
            raise serializers.ValidationError('Invalid credentials')
            
        if not user.is_active:
            raise serializers.ValidationError('User account is disabled')
        
        attrs['user'] = user
        return attrs


# -----------------------------
# Permission Check Serializer
# -----------------------------
class PermissionCheckSerializer(serializers.Serializer):
    """Serializer for checking specific permissions"""
    module = serializers.CharField(required=True)
    action = serializers.CharField(required=False, allow_null=True)
    
    def validate_module(self, value):
        valid_modules = [
            'dashboard', 'sales', 'money_receipt', 'purchases', 'products',
            'accounts', 'customers', 'suppliers', 'expense', 'return',
            'reports', 'users', 'administration', 'settings'
        ]
        
        if value not in valid_modules:
            raise serializers.ValidationError(
                f"Invalid module. Valid modules are: {', '.join(valid_modules)}"
            )
        
        return value
    
    def validate_action(self, value):
        if value:
            valid_actions = ['view', 'create', 'edit', 'delete', 'export']
            if value not in valid_actions:
                raise serializers.ValidationError(
                    f"Invalid action. Valid actions are: {', '.join(valid_actions)}"
                )
        return value