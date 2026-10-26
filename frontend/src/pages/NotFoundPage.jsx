import { Link } from 'react-router-dom'
import { FileQuestion } from 'lucide-react'

export default function NotFoundPage() {
  return (
    <div className="grid min-h-screen place-items-center bg-slate-100 px-4">
      <div className="card max-w-md p-8 text-center">
        <div className="mx-auto mb-4 w-fit rounded-full bg-slate-100 p-3">
          <FileQuestion className="h-7 w-7 text-slate-400" aria-hidden="true" />
        </div>
        <h1 className="text-lg font-bold text-slate-900">Page not found</h1>
        <p className="mt-1.5 text-sm text-slate-600">
          That address does not match any page in SE-EWRS.
        </p>
        <Link to="/" className="btn-primary mt-5">
          Back to the dashboard
        </Link>
      </div>
    </div>
  )
}
