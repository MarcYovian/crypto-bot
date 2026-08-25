import { create } from 'zustand';

export type ToastVariant = 'profit' | 'loss' | 'info' | 'warning';

export interface ToastItem {
  id: string;
  title: string;
  message?: string;
  variant: ToastVariant;
  durationMs?: number;
}

interface ToastState {
  toasts: ToastItem[];
  addToast: (toast: Omit<ToastItem, 'id'>) => void;
  removeToast: (id: string) => void;
}

export const useToastStore = create<ToastState>((set) => ({
  toasts: [],
  addToast: (toast) => {
    const id = Math.random().toString(36).substring(2, 9);
    const newToast: ToastItem = { ...toast, id };

    set((state) => ({
      toasts: [...state.toasts, newToast],
    }));

    const duration = toast.durationMs ?? 4500;
    if (duration > 0) {
      setTimeout(() => {
        set((state) => ({
          toasts: state.toasts.filter((t) => t.id !== id),
        }));
      }, duration);
    }
  },
  removeToast: (id) => {
    set((state) => ({
      toasts: state.toasts.filter((t) => t.id !== id),
    }));
  },
}));

/**
 * Global helper functions for firing toast notifications.
 */
export const toast = {
  profit: (title: string, message?: string) =>
    useToastStore.getState().addToast({ title, message, variant: 'profit' }),
  loss: (title: string, message?: string) =>
    useToastStore.getState().addToast({ title, message, variant: 'loss' }),
  warning: (title: string, message?: string) =>
    useToastStore.getState().addToast({ title, message, variant: 'warning' }),
  info: (title: string, message?: string) =>
    useToastStore.getState().addToast({ title, message, variant: 'info' }),
};
