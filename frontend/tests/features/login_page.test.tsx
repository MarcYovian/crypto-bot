import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { LoginPage } from '@/features/auth/LoginPage';
import { useAuthStore } from '@/stores/authStore';

describe('LoginPage Component', () => {
  beforeEach(() => {
    useAuthStore.getState().clearAuth();
    vi.clearAllMocks();
  });

  it('renders login form elements correctly', () => {
    render(<LoginPage />);

    expect(
      screen.getByRole('heading', { name: /smc cryptobot terminal/i })
    ).toBeInTheDocument();
    expect(screen.getByLabelText(/username/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/^password$/i)).toBeInTheDocument();
    expect(
      screen.getByRole('button', { name: /sign in to terminal/i })
    ).toBeInTheDocument();
  });

  it('toggles password visibility when eye icon clicked', async () => {
    render(<LoginPage />);

    const passwordInput = screen.getByPlaceholderText('••••••••••••');
    expect(passwordInput).toHaveAttribute('type', 'password');

    const toggleButton = screen.getByRole('button', { name: /show password/i });
    await userEvent.click(toggleButton);

    expect(passwordInput).toHaveAttribute('type', 'text');

    const hideButton = screen.getByRole('button', { name: /hide password/i });
    await userEvent.click(hideButton);

    expect(passwordInput).toHaveAttribute('type', 'password');
  });

  it('disables submit button when fields are empty', () => {
    render(<LoginPage />);
    const submitBtn = screen.getByRole('button', { name: /sign in to terminal/i });
    expect(submitBtn).toBeDisabled();
  });

  it('calls login and invokes onLoginSuccess on success', async () => {
    const handleSuccess = vi.fn();
    const mockLogin = vi.fn().mockResolvedValue(true);
    useAuthStore.setState({ login: mockLogin });

    render(<LoginPage onLoginSuccess={handleSuccess} />);

    const usernameInput = screen.getByPlaceholderText('admin');
    const passwordInput = screen.getByPlaceholderText('••••••••••••');
    const submitBtn = screen.getByRole('button', { name: /sign in to terminal/i });

    await userEvent.type(usernameInput, 'admin');
    await userEvent.type(passwordInput, 'AdminPassword123!');
    expect(submitBtn).not.toBeDisabled();

    await userEvent.click(submitBtn);

    expect(mockLogin).toHaveBeenCalledWith({
      username: 'admin',
      password: 'AdminPassword123!',
    });
    expect(handleSuccess).toHaveBeenCalledTimes(1);
  });

  it('displays error alert when auth error exists in store', () => {
    useAuthStore.setState({ error: 'Invalid username or password' });

    render(<LoginPage />);

    expect(screen.getByRole('alert')).toHaveTextContent(
      'Invalid username or password'
    );
  });
});
