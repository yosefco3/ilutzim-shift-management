import { describe, it, expect, vi, afterEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import ConfirmDialog from '../src/components/ConfirmDialog';
import Navbar from '../src/components/Navbar';
import ProtectedRoute from '../src/components/ProtectedRoute';

afterEach(() => {
  localStorage.clear();
});

describe('ConfirmDialog', () => {
  it('renders message and buttons', () => {
    render(
      <ConfirmDialog open message="Are you sure?" onConfirm={vi.fn()} onCancel={vi.fn()} />
    );
    expect(screen.getByText('Are you sure?')).toBeInTheDocument();
    expect(screen.getByText('אישור')).toBeInTheDocument();
    expect(screen.getByText('ביטול')).toBeInTheDocument();
  });

  it('calls onConfirm when confirm clicked', () => {
    const onConfirm = vi.fn();
    render(
      <ConfirmDialog open message="Test" onConfirm={onConfirm} onCancel={vi.fn()} />
    );
    fireEvent.click(screen.getByText('אישור'));
    expect(onConfirm).toHaveBeenCalledOnce();
  });

  it('calls onCancel when cancel clicked', () => {
    const onCancel = vi.fn();
    render(
      <ConfirmDialog open message="Test" onConfirm={vi.fn()} onCancel={onCancel} />
    );
    fireEvent.click(screen.getByText('ביטול'));
    expect(onCancel).toHaveBeenCalledOnce();
  });
});

describe('Navbar', () => {
  it('shows brand and navigation links when authenticated', () => {
    localStorage.setItem('admin_token', 'test');
    render(
      <MemoryRouter>
        <Navbar />
      </MemoryRouter>
    );
    expect(screen.getByText('ניהול מערכת אילוצים')).toBeInTheDocument();
    expect(screen.getByText('מאבטחים')).toBeInTheDocument();
    expect(screen.getByText('שבועות')).toBeInTheDocument();
  });

  it('shows login link when not authenticated', () => {
    render(
      <MemoryRouter>
        <Navbar />
      </MemoryRouter>
    );
    expect(screen.getByText('כניסה')).toBeInTheDocument();
  });
});

describe('ProtectedRoute', () => {
  it('renders children when token exists', () => {
    localStorage.setItem('admin_token', 'valid');
    render(
      <MemoryRouter>
        <ProtectedRoute>
          <div>Secret Content</div>
        </ProtectedRoute>
      </MemoryRouter>
    );
    expect(screen.getByText('Secret Content')).toBeInTheDocument();
  });

  it('does not render children when no token', () => {
    render(
      <MemoryRouter>
        <ProtectedRoute>
          <div>Secret Content</div>
        </ProtectedRoute>
      </MemoryRouter>
    );
    expect(screen.queryByText('Secret Content')).toBeNull();
  });
});