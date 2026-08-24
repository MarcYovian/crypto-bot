import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import {
  Button,
  Badge,
  Input,
  Card,
  CardTitle,
  CardContent,
  Switch,
} from '@/components/ui';

describe('Atomic UI Components (src/components/ui)', () => {
  describe('Button component', () => {
    it('renders text correctly and triggers onClick', async () => {
      const handleClick = vi.fn();
      render(<Button onClick={handleClick}>Click Me</Button>);

      const btn = screen.getByRole('button', { name: /click me/i });
      expect(btn).toBeInTheDocument();

      await userEvent.click(btn);
      expect(handleClick).toHaveBeenCalledTimes(1);
    });

    it('shows loading state and is disabled when isLoading is true', () => {
      render(<Button isLoading>Submit</Button>);
      const btn = screen.getByRole('button');
      expect(btn).toBeDisabled();
      expect(btn).toHaveTextContent('Submit');
    });

    it('applies variant styling classes properly', () => {
      const { rerender } = render(<Button variant="danger">Panic</Button>);
      expect(screen.getByRole('button')).toHaveClass('bg-trading-loss');

      rerender(<Button variant="neon-profit">Execute</Button>);
      expect(screen.getByRole('button')).toHaveClass('bg-trading-profit');
    });
  });

  describe('Badge component', () => {
    it('renders with correct variant classes', () => {
      const { rerender } = render(<Badge variant="profit">BUY / LONG</Badge>);
      expect(screen.getByText('BUY / LONG')).toBeInTheDocument();
      expect(screen.getByText('BUY / LONG')).toHaveClass('text-emerald-400');

      rerender(<Badge variant="loss">SELL / SHORT</Badge>);
      expect(screen.getByText('SELL / SHORT')).toHaveClass('text-rose-400');
    });
  });

  describe('Input component', () => {
    it('renders input with prefix and suffix', () => {
      render(
        <Input
          placeholder="50000"
          prefixNode={<span>$</span>}
          suffixNode={<span>USDT</span>}
        />
      );
      expect(screen.getByPlaceholderText('50000')).toBeInTheDocument();
      expect(screen.getByText('$')).toBeInTheDocument();
      expect(screen.getByText('USDT')).toBeInTheDocument();
    });

    it('applies error border when isError is true', () => {
      render(<Input placeholder="Error field" isError />);
      expect(screen.getByPlaceholderText('Error field')).toHaveClass('border-trading-loss');
    });
  });

  describe('Card component', () => {
    it('renders card title and content', () => {
      render(
        <Card>
          <CardTitle>Total Balance</CardTitle>
          <CardContent>$10,450.50</CardContent>
        </Card>
      );
      expect(screen.getByText('Total Balance')).toBeInTheDocument();
      expect(screen.getByText('$10,450.50')).toBeInTheDocument();
    });
  });

  describe('Switch component', () => {
    it('toggles state on click', async () => {
      const handleChange = vi.fn();
      render(<Switch onCheckedChange={handleChange} aria-label="Toggle Feature" />);

      const toggle = screen.getByRole('switch', { name: /toggle feature/i });
      expect(toggle).toBeInTheDocument();

      await userEvent.click(toggle);
      expect(handleChange).toHaveBeenCalledWith(true);
    });
  });
});
